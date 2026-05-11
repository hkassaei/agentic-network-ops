"""Tests for the TF-IDF embedder.

The embedder is one half of R2's contract (the other being the
index). The two contracts that matter:

  1. **Determinism** — re-running `fit + encode` on the same input
     must return identical vectors. Without this, the persisted
     embeddings.npy in a saved index is meaningless across rebuilds.

  2. **Cosine alignment** — the row vectors must be L2-normalized,
     so the index module can compute cosine similarity as a plain
     dot product.
"""

from __future__ import annotations

import numpy as np
import pytest

from agentic_ops_common.rag.embedder import TfidfEmbedder


_TINY_CORPUS = [
    "derived.rtpengine_loss_ratio:spike:MEDIUM\nscenario: Call Quality Degradation",
    "normalized.upf.gtp_indatapktn3upf_per_ue:drop:MEDIUM\nscenario: Data Plane Degradation",
    "derived.icscf_uar_timeout_ratio:spike:HIGH\nscenario: HSS Unresponsive",
]


def test_embedder_fits_and_encodes():
    e = TfidfEmbedder()
    e.fit(_TINY_CORPUS)
    encoded = e.encode(_TINY_CORPUS)
    assert encoded.shape[0] == len(_TINY_CORPUS)
    assert encoded.shape[1] == e.embed_dim
    assert encoded.dtype == np.float32


def test_embedder_is_deterministic_across_runs():
    """Two independent fit+encode cycles on the same input must
    return bit-identical vectors. If this breaks, persisted indexes
    become unreloadable across process restarts."""
    e1 = TfidfEmbedder()
    e1.fit(_TINY_CORPUS)
    v1 = e1.encode(_TINY_CORPUS)

    e2 = TfidfEmbedder()
    e2.fit(_TINY_CORPUS)
    v2 = e2.encode(_TINY_CORPUS)

    np.testing.assert_array_equal(v1, v2)


def test_embedder_output_is_l2_normalized():
    """Row vectors must be unit-norm so the index's dot-product
    similarity == cosine similarity."""
    e = TfidfEmbedder()
    e.fit(_TINY_CORPUS)
    v = e.encode(_TINY_CORPUS)
    norms = np.linalg.norm(v, axis=1)
    np.testing.assert_allclose(norms, np.ones(len(_TINY_CORPUS)), atol=1e-6)


def test_embedder_raises_when_used_before_fit():
    """encode() before fit() must fail loud, not silently produce
    nonsense zero vectors."""
    e = TfidfEmbedder()
    with pytest.raises(RuntimeError, match="before fit"):
        e.encode(["any text"])


def test_embedder_empty_corpus_leaves_unfitted():
    """fit([]) is tolerated for cold-start; subsequent encode()
    raises, signaling the caller to retry once they have data."""
    e = TfidfEmbedder()
    e.fit([])
    assert e.embed_dim == 0
    with pytest.raises(RuntimeError):
        e.encode(["x"])


def test_embedder_signature_overlap_drives_similarity():
    """Two query texts that share a flag signature should embed
    closer to each other than to an unrelated query. This is the
    intuitive contract that makes RAG useful at all."""
    e = TfidfEmbedder()
    e.fit(_TINY_CORPUS)
    # Two queries about rtpengine loss vs one about HSS Cx timeout.
    queries = [
        "derived.rtpengine_loss_ratio:spike:HIGH",     # similar to corpus[0]
        "derived.rtpengine_loss_ratio:spike:MEDIUM",   # identical to corpus[0] mod severity
        "derived.icscf_uar_timeout_ratio:spike:HIGH",  # similar to corpus[2]
    ]
    v = e.encode(queries)
    # cosine similarity matrix between queries (vectors are L2-norm'd
    # so a dot product is enough).
    sim = v @ v.T
    # rtpengine ↔ rtpengine should be more similar than rtpengine ↔ hss.
    assert sim[0, 1] > sim[0, 2], (
        f"Two rtpengine queries (sim={sim[0,1]:.3f}) should be more similar "
        f"to each other than either is to an HSS query (sim={sim[0,2]:.3f})."
    )
