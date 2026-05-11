"""Retrieval-Augmented Generation (RAG) corpus building blocks.

This package is shared infrastructure for indexing past chaos-episode
outcomes into a retrievable corpus that agent prompts can draw from.
It lives under `agentic_ops_common` so every agent generation
(v5, v6, v7, future) speaks the same case-schema vocabulary.

Step R1 — this package — provides:

  - `FlagSummary`     a single anomaly-screener flag row, in a form
                     compact enough to embed as part of a retrieval key.
  - `RetrievedCase`   one retrievable unit. Carries the case's identity,
                     scenario, ground truth, screener output, agent
                     diagnosis, and score. Two render methods on top:
                       * `retrieval_key_text()` — what gets embedded
                       * `render_for_prompt(...)` — what gets injected
                         into an agent prompt at retrieval time.
  - `parse_episode`   reads a single `run_*.json` (preferred) or
                     `run_*.md` (fallback) and returns a populated
                     `RetrievedCase`, or `None` with a logged reason.
  - `parse_corpus`    walks a list of `docs/agent_logs/` directories
                     and returns the full list of parsed cases.
  - CLI               `python -m agentic_ops_common.rag.parser stats
                     <dir> [<dir> ...]` prints corpus statistics; the
                     smoke test for R1.

What R1 does NOT do (deliberate scope boundary):

  - No embedding, no vector store, no retrieval API, no prompt wiring,
    no corpus filtering by score. Those land in R2-R4 (see
    `docs/work-plan-may-11.md`).
"""

from .schema import FlagSummary, RetrievedCase
from .parser import parse_corpus, parse_episode
from .embedder import Embedder, TfidfEmbedder
from .index import CaseIndex, IndexManifest, SearchHit
from .retriever import (
    EpisodeRetriever,
    get_default_retriever,
    reset_default_retriever_cache,
)
from .lessons import (
    DEFAULT_LESSONS_PATH,
    Lesson,
    load_lessons,
    render_lessons_for_prompt,
    try_load_lessons,
)

__all__ = [
    # Schema (R1)
    "FlagSummary",
    "RetrievedCase",
    # Parser (R1)
    "parse_corpus",
    "parse_episode",
    # Embedder (R2)
    "Embedder",
    "TfidfEmbedder",
    # Index (R2)
    "CaseIndex",
    "IndexManifest",
    "SearchHit",
    # Retriever (R3)
    "EpisodeRetriever",
    "get_default_retriever",
    "reset_default_retriever_cache",
    # Lessons (R5)
    "DEFAULT_LESSONS_PATH",
    "Lesson",
    "load_lessons",
    "render_lessons_for_prompt",
    "try_load_lessons",
]
