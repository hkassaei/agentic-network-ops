"""Embedder protocol + default TF-IDF implementation.

The retrieval-key text produced by `RetrievedCase.retrieval_key_text()`
is a structured list of flag signatures
(`derived.rtpengine_loss_ratio:spike:MEDIUM`) plus a scenario suffix.
Similarity between two cases is dominated by overlap in these
signatures — which is a textbook fit for **TF-IDF cosine similarity**:
each signature acts as a token, the IDF weighting downplays
"appears in everything" signatures (e.g. UPF GTP drops that get
flagged in over-flagging cases), and cosine similarity gives a clean
0-1 score.

Deviation from the work plan (which named FAISS + sentence-transformers
as the default stack): neither dependency is installed in this venv,
and adding torch + transformers would pull in ~1GB. The 97-case
filtered corpus is far too small for FAISS's nearest-neighbour
indexing to matter — naive numpy cosine similarity does the job in
under 50ms. scikit-learn is already installed. When the corpus grows
past ~10K units, swap in a richer `Embedder` implementation behind
the same protocol — the indexer doesn't know which embedder it has.

Future implementations the protocol leaves room for:

  - `GeminiEmbedder` via `google.genai` (text-embedding-004). Adds
    semantic richness at the cost of one API call per indexed unit
    (~$0.0001 each). Already installed.
  - `SentenceTransformerEmbedder` for fully-local semantic embeddings.
    Needs `pip install sentence-transformers`.
"""

from __future__ import annotations

from typing import Protocol, Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


class Embedder(Protocol):
    """Protocol every embedding backend implements.

    Two operations:

      `fit(corpus)`  — learn whatever priors the embedder needs from
                       the corpus (TF-IDF vocabulary + IDF weights;
                       a learned embedder may no-op here).
      `encode(text)` — turn one or more texts into row vectors.

    `embed_dim` is exposed so callers (and on-disk manifests) can
    record the embedding-space dimensionality without instantiating
    the embedder.

    Determinism is a hard requirement — re-running an index build
    from the same corpus must produce identical embeddings, or
    similarity comparisons across runs become unstable.
    """

    name: str
    """Stable identifier — recorded in the index manifest so loaders
    know which embedder produced the persisted state."""

    @property
    def embed_dim(self) -> int: ...

    def fit(self, corpus: Sequence[str]) -> None: ...

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Returns a 2-D array shape (len(texts), embed_dim)."""
        ...


class TfidfEmbedder:
    """Default embedder — sklearn TF-IDF + L2-normalized dense output.

    The dense output is small (~1000-dim vocab × 97 cases = ~775 KB
    in float32), well within memory at this scale and lets the
    caller use plain `numpy.dot` for cosine similarity. When the
    corpus grows past ~10K units, switch to a sparse-aware indexer
    or a different embedder.

    L2 normalization is applied at `encode` time so that cosine
    similarity reduces to a dot product downstream. This keeps the
    search code in `CaseIndex` independent of the embedder choice.

    Tokenization rules: lower-cased, split on whitespace and on dots
    / colons / underscores so flag signatures decompose into useful
    tokens. The flag `derived.rtpengine_loss_ratio:spike:MEDIUM`
    becomes the token set `{derived, rtpengine, loss, ratio, spike,
    medium}` — overlapping pieces between two flags count as
    similarity even when the full signatures don't match exactly.
    """

    name = "tfidf-v1"

    def __init__(
        self,
        *,
        min_df: int = 1,
        max_df: float = 0.95,
        ngram_range: tuple[int, int] = (1, 2),
    ) -> None:
        # `token_pattern` accepts any run of word chars OR keeps colons
        # so signatures' direction/severity suffixes survive. We split
        # on dots/colons/underscores via a custom token_pattern that
        # treats those as separators (the default `\b\w\w+\b` already
        # does this for dots/colons, but we want explicit control).
        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            token_pattern=r"[a-zA-Z][a-zA-Z0-9]+",
            min_df=min_df,
            max_df=max_df,
            ngram_range=ngram_range,
            norm="l2",  # row-normalize for cosine via dot product
            sublinear_tf=True,
        )
        self._fitted = False

    @property
    def embed_dim(self) -> int:
        if not self._fitted:
            return 0
        return len(self._vectorizer.vocabulary_)

    def fit(self, corpus: Sequence[str]) -> None:
        """Learn the vocabulary + IDF weights from the corpus.

        Empty corpus is tolerated for cold-start cases; subsequent
        encode() calls will return zero-dim vectors until fit() is
        called with real text.
        """
        if not corpus:
            self._fitted = False
            return
        self._vectorizer.fit(corpus)
        self._fitted = True

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Encode texts to L2-normalized dense vectors.

        Raises `RuntimeError` if called before `fit()` — failing
        loud is better than silently returning zero vectors that
        produce nonsense similarity scores downstream.
        """
        if not self._fitted:
            raise RuntimeError(
                "TfidfEmbedder.encode() called before fit(). Call "
                "fit(corpus) once with the full retrieval-key corpus, "
                "then encode() any subset."
            )
        if not texts:
            return np.zeros((0, self.embed_dim), dtype=np.float32)
        sparse = self._vectorizer.transform(texts)
        # toarray() is fine at this scale; float32 halves the memory.
        return np.asarray(sparse.toarray(), dtype=np.float32)
