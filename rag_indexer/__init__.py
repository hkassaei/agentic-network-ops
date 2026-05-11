"""RAG case-index builder for the agentic-ops pipeline.

Walks chaos-episode files under one or more `docs/agent_logs/`
directories, parses each episode into a `RetrievedCase`, filters to
score ≥ threshold, embeds the retrieval-key text via the shipped
TF-IDF embedder, and persists the index as
`<output>/manifest.json + cases.jsonl + embeddings.npy`. At runtime
the v7 orchestrator's Phase 2.5 helper auto-discovers the index at
`<repo>/rag_index/` (or via the `RAG_INDEX_DIR` env var) and injects
top-K prior cases into the NetworkAnalyst's prompt.

Usage:
    python -m rag_indexer

    python -m rag_indexer --output ./rag_index_alt --score-threshold 100

    python -m rag_indexer --help

This module is the operator-facing companion to the agentic-ops
RAG infrastructure shipped in `agentic_ops_common/rag/` (R1-R5
in `docs/work-plan-may-11.md` and the
`rag_episode_retrieval_and_lesson_injection.md` ADR).

Sibling tools follow the same invocation convention:

    python -m anomaly_trainer            # train the screener
    python -m agentic_chaos run …        # run a chaos scenario
    python -m rag_indexer                # build the RAG index
"""
