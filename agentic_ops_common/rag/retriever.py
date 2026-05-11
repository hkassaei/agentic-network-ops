"""EpisodeRetriever — runtime RAG case lookup for agent prompts.

The RAG indexer (R2) produces a `CaseIndex` on disk. At investigation
time, the orchestrator wants a small, well-scoped API to:

  1. Load the index once per process (cached).
  2. Build a retrieval query from the live anomaly screener output.
  3. Fetch the top-K most-similar prior cases.
  4. Format them as a markdown block ready to inject into a prompt
     (currently NetworkAnalyst at Phase 3; later possibly Synthesis).

`EpisodeRetriever` is that API. It is a thin wrapper over `CaseIndex`:
the index does the actual cosine-similarity work; the retriever adds
ergonomics around live-screener-output ingestion and prompt-block
rendering.

Two failure modes the retriever handles gracefully:

  - **Index missing on disk.** Some environments may not have an
    index built yet (cold start, CI without the chaos-log artifacts).
    `try_from_path()` returns `None` instead of raising so the
    orchestrator can fall through to a no-RAG path. Hard
    `from_path()` is available for environments that want to fail
    loud when the index is genuinely required.

  - **Empty result set.** `render_hits_for_prompt([])` returns the
    empty string, signaling the caller's prompt template to render a
    "no sufficiently similar prior episode in the corpus" note in
    its place — never injecting weakly-relevant noise.

This module is version-agnostic (lives under `agentic_ops_common/`)
so v7 and any future agent generation share the same retriever
contract.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence

from agentic_ops_common.anomaly.screener import AnomalyFlag

from .index import CaseIndex, SearchHit
from .schema import FlagSummary

log = logging.getLogger("agentic_ops_common.rag.retriever")


class EpisodeRetriever:
    """Runtime retriever for RAG case lookups."""

    def __init__(self, index: CaseIndex) -> None:
        self._index = index

    # ── Constructors ────────────────────────────────────────────────

    @classmethod
    def from_path(cls, index_dir: Path | str) -> "EpisodeRetriever":
        """Load an index from disk.

        Raises `FileNotFoundError` if the directory is missing or
        doesn't contain a manifest. Use `try_from_path()` for
        graceful handling.
        """
        return cls(CaseIndex.load(index_dir))

    @classmethod
    def try_from_path(cls, index_dir: Path | str) -> Optional["EpisodeRetriever"]:
        """Load an index, returning None if it's missing or unreadable.

        The orchestrator uses this to opt-in to RAG: if the index
        is present, retrieve; otherwise, run the pipeline without
        prior-case injection. RAG-disabled is a no-op, not an error.
        """
        try:
            return cls.from_path(index_dir)
        except FileNotFoundError as e:
            log.info("RAG index unavailable at %s (%s); RAG disabled.", index_dir, e)
            return None
        except Exception as e:
            log.warning(
                "RAG index at %s failed to load: %s; RAG disabled.",
                index_dir, e, exc_info=True,
            )
            return None

    # ── Retrieval ───────────────────────────────────────────────────

    def retrieve(
        self,
        query_text: str,
        *,
        k: int = 5,
        min_similarity: float = 0.65,
    ) -> list[SearchHit]:
        """Generic retrieval. `query_text` is whatever the caller wants
        to embed — typically a `RetrievedCase.retrieval_key_text()`-
        shaped string built from the live screener output.

        `min_similarity` default (0.65) is the prompt-injection floor:
        below this the case is treated as "not really similar," and
        injecting it would confuse the agent more than help. Override
        for diagnostic / audit views.
        """
        return self._index.search(
            query_text, k=k, min_similarity=min_similarity,
        )

    def retrieve_for_flags(
        self,
        flags: Sequence[AnomalyFlag | FlagSummary | dict],
        *,
        k: int = 5,
        min_similarity: float = 0.65,
        scenario_hint: Optional[str] = None,
        classifier_label: Optional[str] = None,
    ) -> list[SearchHit]:
        """Convenience: build a retrieval query from a live screener's
        flag list (or any equivalent representation) and retrieve.

        Accepted shapes for `flags`:
          - `AnomalyFlag` from the live screener (with kb_context).
          - `FlagSummary` from the RAG schema.
          - Dict from `AnomalyReport.to_dict_list()`.

        `scenario_hint` and `classifier_label` append weak suffixes to
        the query (mirroring `RetrievedCase.retrieval_key_text()`'s
        layout) — useful when the orchestrator knows them at retrieval
        time. Both are optional; omitting them just drops the suffix.
        """
        query_text = _build_query_text_from_flags(
            flags, scenario_hint=scenario_hint, classifier_label=classifier_label,
        )
        if not query_text:
            return []
        return self.retrieve(query_text, k=k, min_similarity=min_similarity)

    # ── Rendering ───────────────────────────────────────────────────

    @staticmethod
    def render_hits_for_prompt(
        hits: Sequence[SearchHit],
        *,
        verbosity: str = "default",
        header: str = "## Prior similar episodes",
    ) -> str:
        """Format hits as a markdown block ready for prompt injection.

        Layout:

          ## Prior similar episodes
          *(N retrieved at min-similarity X; each cites source path.)*

          ### Rank 1 — similarity 62%
          <case.render_for_prompt(verbosity)>

          ### Rank 2 — similarity 58%
          <case.render_for_prompt(verbosity)>
          ...

        Returns the empty string for empty hits — callers should
        substitute a "no sufficiently similar prior episode" note in
        the prompt itself, so the agent sees an explicit absence
        rather than a missing section.

        Similarity is rendered as an integer percent because absolute
        cosine values aren't very interpretable; relative ranking and
        a coarse percent are.
        """
        if not hits:
            return ""

        lines: list[str] = [header, ""]
        lines.append(
            f"*({len(hits)} prior case(s) retrieved by signature similarity. "
            f"Each cites its source episode path — the EvidenceValidator can "
            f"audit any case you reference.)*"
        )
        lines.append("")

        for hit in hits:
            sim_pct = int(round(hit.similarity * 100))
            lines.append(f"### Rank {hit.rank + 1} — similarity {sim_pct}%")
            lines.append("")
            lines.append(hit.case.render_for_prompt(verbosity))
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    # ── Introspection ───────────────────────────────────────────────

    @property
    def case_count(self) -> int:
        """Number of cases the retriever has access to. 0 means the
        index is empty (cold start)."""
        return len(self._index.cases)

    @property
    def index(self) -> CaseIndex:
        """Direct access to the underlying CaseIndex. Use sparingly —
        prefer the retriever's API for normal use."""
        return self._index


# ─────────────────────────────────────────────────────────────────────
# Singleton accessor
# ─────────────────────────────────────────────────────────────────────


_DEFAULT_RETRIEVERS: dict[str, EpisodeRetriever] = {}


def get_default_retriever(
    index_dir: Path | str,
    *,
    refresh: bool = False,
) -> Optional[EpisodeRetriever]:
    """Process-cached accessor for a retriever loaded from `index_dir`.

    First call with a given `index_dir` loads the index from disk.
    Subsequent calls return the cached retriever. Pass `refresh=True`
    to force a reload (useful after rebuilding the index without
    restarting the process).

    Returns `None` when the index is missing or unreadable — same
    semantics as `EpisodeRetriever.try_from_path()`. The orchestrator
    treats `None` as "RAG disabled" and runs without prior-case
    injection.

    Caching is keyed on the absolute string form of `index_dir`. Two
    callers using equivalent-but-differently-spelled paths get the
    same cached retriever via path resolution.
    """
    key = str(Path(index_dir).resolve())
    if refresh:
        _DEFAULT_RETRIEVERS.pop(key, None)
    if key in _DEFAULT_RETRIEVERS:
        return _DEFAULT_RETRIEVERS[key]

    retriever = EpisodeRetriever.try_from_path(index_dir)
    if retriever is not None:
        _DEFAULT_RETRIEVERS[key] = retriever
    return retriever


def reset_default_retriever_cache() -> None:
    """Clear the process-level retriever cache. Used by tests to keep
    each test's retriever isolated from the others'."""
    _DEFAULT_RETRIEVERS.clear()


# ─────────────────────────────────────────────────────────────────────
# Query construction
# ─────────────────────────────────────────────────────────────────────


def _build_query_text_from_flags(
    flags: Sequence[AnomalyFlag | FlagSummary | dict],
    *,
    scenario_hint: Optional[str] = None,
    classifier_label: Optional[str] = None,
) -> str:
    """Render a list of flags as a query string in the same shape that
    `RetrievedCase.retrieval_key_text()` uses for the indexed corpus.

    The flag's signature is `component.metric:direction:severity`,
    matching what the indexer embedded. Suffix lines (scenario,
    classifier) are appended only when their hints are provided.
    """
    signatures: list[str] = []
    for f in flags:
        sig = _flag_signature(f)
        if sig:
            signatures.append(sig)

    if not signatures and not scenario_hint and not classifier_label:
        return ""

    lines: list[str] = list(signatures)
    if scenario_hint:
        lines.append(f"scenario: {scenario_hint}")
    if classifier_label:
        lines.append(f"classifier: {classifier_label}")
    return "\n".join(lines)


def _flag_signature(flag: AnomalyFlag | FlagSummary | dict) -> Optional[str]:
    """Extract a signature string from any of the accepted flag shapes."""
    if isinstance(flag, FlagSummary):
        return flag.signature()

    if isinstance(flag, AnomalyFlag):
        # AnomalyFlag stores (metric, component, direction, severity)
        # — same shape as FlagSummary.signature() except FlagSummary's
        # `component` is the screener's prefix and `metric` is the rest.
        if not flag.metric or not flag.component:
            return None
        direction = flag.direction or "shift"
        severity = flag.severity or "LOW"
        return f"{flag.component}.{flag.metric}:{direction}:{severity}"

    if isinstance(flag, dict):
        # AnomalyReport.to_dict_list() output, or any compatible dict.
        component = flag.get("component", "")
        metric = flag.get("metric", "")
        direction = flag.get("direction", "shift")
        severity = flag.get("severity", "LOW")
        if not component or not metric:
            return None
        return f"{component}.{metric}:{direction}:{severity}"

    return None
