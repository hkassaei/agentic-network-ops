"""CaseIndex — the indexed RAG corpus + similarity search.

`CaseIndex` is the R2-shipped vector index over `RetrievedCase`
units. Three operations on it:

  - `build(cases, embedder)` — embed every case's
    `retrieval_key_text()` into an embedding matrix.
  - `save(directory) / load(directory)` — persist the index to disk
    so the runtime retriever (R3) doesn't have to re-embed.
  - `search(query_text, k, min_similarity)` — encode a query,
    cosine-rank the indexed cases, return the top-K above the
    similarity floor.

Persistence format (a directory):

  `manifest.json`   build metadata (embedder name + dim, case count,
                    score threshold, build timestamp). Cheap to
                    inspect; tells loaders what they're dealing with.
  `cases.jsonl`     one JSON object per case (RetrievedCase.model_dump
                    output), ordered to match the embedding rows.
  `embeddings.npy`  numpy array shape (n_cases, embed_dim), float32.

The vectorizer's internal state is NOT pickled — we rebuild it on
`load()` by re-fitting the embedder on the persisted retrieval-key
corpus. Slightly slower load (~50ms for 100 cases) but robust against
sklearn version drift; pickled vectorizers break on upgrade.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from .embedder import Embedder, TfidfEmbedder
from .schema import RetrievedCase

log = logging.getLogger("agentic_ops_common.rag.index")


# ─────────────────────────────────────────────────────────────────────
# Search result
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SearchHit:
    """One ranked retrieval result.

    `similarity` is cosine similarity in [0, 1]. Higher = more similar.
    Callers use it to threshold low-confidence matches before injecting
    cases into a prompt.
    """
    case: RetrievedCase
    similarity: float
    rank: int  # 0-indexed position in the result list


# ─────────────────────────────────────────────────────────────────────
# Index manifest — the on-disk metadata blob
# ─────────────────────────────────────────────────────────────────────


@dataclass
class IndexManifest:
    """On-disk metadata describing a built index."""
    embedder_name: str
    embed_dim: int
    case_count: int
    score_threshold: int            # the score % filter the build applied
    built_at: str                   # ISO-8601 UTC
    builder_version: str = "r2-v1"  # bump when on-disk format changes

    def to_dict(self) -> dict:
        return {
            "embedder_name": self.embedder_name,
            "embed_dim": self.embed_dim,
            "case_count": self.case_count,
            "score_threshold": self.score_threshold,
            "built_at": self.built_at,
            "builder_version": self.builder_version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IndexManifest":
        return cls(
            embedder_name=d["embedder_name"],
            embed_dim=int(d["embed_dim"]),
            case_count=int(d["case_count"]),
            score_threshold=int(d["score_threshold"]),
            built_at=d["built_at"],
            builder_version=d.get("builder_version", "r2-v1"),
        )


# ─────────────────────────────────────────────────────────────────────
# CaseIndex
# ─────────────────────────────────────────────────────────────────────


@dataclass
class CaseIndex:
    """In-memory representation of a built RAG index.

    Always constructed via one of the class methods (`build`, `load`)
    — not via `__init__` directly. The fields below are populated by
    those constructors.
    """
    cases: list[RetrievedCase] = field(default_factory=list)
    embeddings: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 0), dtype=np.float32),
    )
    embedder: Optional[Embedder] = None
    manifest: Optional[IndexManifest] = None

    # ── Builders ────────────────────────────────────────────────────

    @classmethod
    def build(
        cls,
        cases: list[RetrievedCase],
        embedder: Optional[Embedder] = None,
        *,
        score_threshold: int = 80,
    ) -> "CaseIndex":
        """Build an in-memory index from a list of parsed cases.

        Cases below `score_threshold` are excluded — they're either
        wrong-answer episodes (no positive teaching signal) or
        require hand-distilled lesson units (R5 territory). The
        default 80 matches the work plan's corpus eligibility rule.

        Empty `cases` is tolerated and produces a degenerate index
        that returns no hits on search. Useful for unit tests and
        cold-start environments.
        """
        if embedder is None:
            embedder = TfidfEmbedder()

        filtered = [c for c in cases if c.score_pct >= score_threshold]
        log.info(
            "Building index: %d / %d cases pass score_threshold=%d",
            len(filtered), len(cases), score_threshold,
        )

        retrieval_texts = [c.retrieval_key_text() for c in filtered]
        embedder.fit(retrieval_texts)
        embeddings = (
            embedder.encode(retrieval_texts)
            if retrieval_texts else np.zeros((0, 0), dtype=np.float32)
        )

        manifest = IndexManifest(
            embedder_name=embedder.name,
            embed_dim=int(embedder.embed_dim),
            case_count=len(filtered),
            score_threshold=score_threshold,
            built_at=datetime.now(timezone.utc).isoformat(),
        )

        return cls(
            cases=filtered,
            embeddings=embeddings,
            embedder=embedder,
            manifest=manifest,
        )

    # ── Persistence ─────────────────────────────────────────────────

    def save(self, directory: Path | str) -> None:
        """Persist to disk as manifest.json + cases.jsonl + embeddings.npy.

        Creates the directory if missing. Existing contents are
        overwritten — the index is a build artifact, not a journal.
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        if self.manifest is None:
            raise RuntimeError(
                "CaseIndex.save() called on an index that has no "
                "manifest. Did you forget to call .build() first?"
            )

        # manifest.json — human-readable, cheap to inspect.
        (directory / "manifest.json").write_text(
            json.dumps(self.manifest.to_dict(), indent=2) + "\n"
        )

        # cases.jsonl — one case per line, parallel to embedding rows.
        with (directory / "cases.jsonl").open("w") as fh:
            for case in self.cases:
                fh.write(case.model_dump_json() + "\n")

        # embeddings.npy — float32, shape (n_cases, embed_dim).
        np.save(directory / "embeddings.npy", self.embeddings.astype(np.float32))

        log.info(
            "Index saved to %s (%d cases, embed_dim=%d)",
            directory, len(self.cases), self.embeddings.shape[1] if self.embeddings.size else 0,
        )

    @classmethod
    def load(cls, directory: Path | str) -> "CaseIndex":
        """Load a previously-saved index.

        Rebuilds the embedder by re-fitting on the persisted
        retrieval-key corpus — see this module's docstring for the
        version-drift rationale. The persisted `embeddings.npy` is
        kept as the canonical case embeddings (we don't re-encode
        the corpus on load, because that would produce slightly
        different float32 values across sklearn versions). The
        embedder is only used to encode *query* texts at search
        time, where the relative cosine ranking matters more than
        absolute numeric stability.
        """
        directory = Path(directory)
        if not (directory / "manifest.json").exists():
            raise FileNotFoundError(
                f"No manifest.json in {directory}; not a CaseIndex directory."
            )

        manifest = IndexManifest.from_dict(
            json.loads((directory / "manifest.json").read_text())
        )

        cases: list[RetrievedCase] = []
        with (directory / "cases.jsonl").open("r") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                cases.append(RetrievedCase.model_validate_json(line))

        embeddings = np.load(directory / "embeddings.npy").astype(np.float32)

        # Rebuild the embedder by re-fitting on the same retrieval-key
        # corpus. Determinism is preserved by the embedder itself
        # (TfidfEmbedder uses a fixed vocabulary-build seed).
        embedder = _select_embedder_for(manifest.embedder_name)
        retrieval_texts = [c.retrieval_key_text() for c in cases]
        embedder.fit(retrieval_texts)

        log.info(
            "Index loaded from %s (%d cases, embedder=%s, dim=%d)",
            directory, len(cases), manifest.embedder_name, manifest.embed_dim,
        )

        return cls(
            cases=cases,
            embeddings=embeddings,
            embedder=embedder,
            manifest=manifest,
        )

    # ── Search ──────────────────────────────────────────────────────

    def search(
        self,
        query_text: str,
        *,
        k: int = 5,
        min_similarity: float = 0.0,
    ) -> list[SearchHit]:
        """Cosine-rank cases against the query and return the top-K.

        Args:
          query_text: typically a `RetrievedCase.retrieval_key_text()`-
            shaped string built from the current episode's screener
            output.
          k: max hits to return.
          min_similarity: cosine-similarity floor; hits below are
            dropped from the result. 0.0 returns the top-K regardless
            of how weak the match is.

        Empty index, empty query, and zero-norm query all produce
        an empty result list rather than raising.
        """
        if not self.cases or self.embeddings.size == 0:
            return []
        if not query_text or self.embedder is None:
            return []

        query_vec = self.embedder.encode([query_text])  # shape (1, dim)
        if query_vec.shape[1] == 0:
            return []

        # Embeddings are already L2-normalized (TfidfEmbedder's norm="l2").
        # If a custom embedder skipped that, normalize here defensively.
        embeddings = _l2_normalize(self.embeddings)
        query_norm = _l2_normalize(query_vec)

        # Dot product on row-normalized vectors == cosine similarity.
        similarities = (embeddings @ query_norm.T).ravel()
        # Get top-K indices sorted by descending similarity.
        if k >= len(similarities):
            ranked_idx = np.argsort(-similarities)
        else:
            top_k_unsorted = np.argpartition(-similarities, k)[:k]
            ranked_idx = top_k_unsorted[np.argsort(-similarities[top_k_unsorted])]

        hits: list[SearchHit] = []
        for rank, idx in enumerate(ranked_idx[:k]):
            sim = float(similarities[idx])
            if sim < min_similarity:
                continue
            hits.append(SearchHit(
                case=self.cases[int(idx)],
                similarity=sim,
                rank=rank,
            ))
        return hits


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _select_embedder_for(name: str) -> Embedder:
    """Construct an Embedder matching a persisted manifest's name.

    For now we ship one embedder; this dispatcher exists so the on-disk
    manifest's `embedder_name` field is load-bearing — a future
    GeminiEmbedder gets registered here without touching index callers.
    """
    if name == TfidfEmbedder.name:
        return TfidfEmbedder()
    raise ValueError(
        f"Unknown embedder_name in manifest: {name!r}. "
        f"Known: {[TfidfEmbedder.name]}"
    )


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalize. Zero-norm rows stay zero (rather than NaN)."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe = np.where(norms == 0, 1.0, norms)
    return matrix / safe
