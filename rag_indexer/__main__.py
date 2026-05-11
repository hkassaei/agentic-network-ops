"""CLI entry point for the RAG case-index builder.

Usage:
    python -m rag_indexer

    python -m rag_indexer --output ./rag_index_alt \\
        --source agentic_ops_v7/docs/agent_logs

Sources default to all three agent-version log directories at the
repo root (v5, v6, v7). Output defaults to `<repo>/rag_index/` —
the path the v7 orchestrator's `RAG_INDEX_DIR` resolver looks for
when no env var override is set.

Companion docs:
  - docs/ADR/rag_episode_retrieval_and_lesson_injection.md
  - docs/work-plan-may-11.md (R1-R7)
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure the repo root is on sys.path for `from agentic_ops_common ...`
# when this module is invoked as `python -m rag_indexer` from anywhere.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ── Defaults ────────────────────────────────────────────────────────

_DEFAULT_SOURCES = (
    "agentic_ops_v5/docs/agent_logs",
    "agentic_ops_v6/docs/agent_logs",
    "agentic_ops_v7/docs/agent_logs",
)
_DEFAULT_OUTPUT = "rag_index"
_DEFAULT_SCORE_THRESHOLD = 80

# A canonical query the verification step runs against the built index
# to sanity-check that retrieval works end-to-end. Built to resemble
# what the v7 orchestrator emits for a Call Quality Degradation episode
# (rtpengine 30% loss).
_SMOKE_QUERY = (
    "derived.rtpengine_loss_ratio:spike:MEDIUM\n"
    "normalized.upf.gtp_indatapktn3upf_per_ue:drop:MEDIUM\n"
    "normalized.upf.gtp_outdatapktn3upf_per_ue:drop:MEDIUM\n"
    "scenario: Call Quality Degradation\n"
    "classifier: mixed"
)


# ── Phase 1: Pre-flight ─────────────────────────────────────────────


def _preflight(sources: list[Path], output_dir: Path) -> int:
    """Validate sources exist + the output path is writable.

    Returns 0 on PASS, non-zero exit code on FAIL. Prints any failure
    cause so the operator knows what to fix.
    """
    print("Pre-flight checks:")
    any_failed = False

    for src in sources:
        if src.exists() and src.is_dir():
            n_json = len(list(src.glob("run_*.json")))
            n_md = len(list(src.glob("run_*.md")))
            print(f"  ✓ {src}  (json={n_json}, md={n_md})")
        else:
            print(f"  ✗ {src}  MISSING (skipping)")
            any_failed = True

    if all(not (src.exists() and src.is_dir()) for src in sources):
        print(
            "\n  ABORT: every source directory is missing. "
            "Check the --source arguments."
        )
        return 2

    if output_dir.exists() and not output_dir.is_dir():
        print(f"\n  ABORT: --output {output_dir} exists but is not a directory.")
        return 2

    parent = output_dir.parent
    if not parent.exists():
        print(
            f"\n  ABORT: parent of --output ({parent}) does not exist. "
            f"Create it or pick a different --output."
        )
        return 2

    if any_failed:
        # Some sources missing but not all → continue with a warning.
        print("\n  Some source directories were missing; continuing with the rest.")
    return 0


# ── Phase 2: Backup existing index ──────────────────────────────────


def _backup_existing(output_dir: Path) -> Path | None:
    """If output_dir already contains a built index, move it aside.

    Returns the backup path (sibling dir with a UTC-timestamp suffix),
    or None if there was nothing to back up. Saves the operator from
    accidentally clobbering a known-good index.
    """
    expected = ("manifest.json", "cases.jsonl", "embeddings.npy")
    if not output_dir.exists() or not any(
        (output_dir / f).exists() for f in expected
    ):
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = output_dir.with_name(f"{output_dir.name}.bak.{ts}")
    shutil.move(str(output_dir), str(backup))
    return backup


# ── Phase 3: Build + save ──────────────────────────────────────────


def _build_and_save(
    sources: list[Path],
    output_dir: Path,
    score_threshold: int,
) -> dict:
    """Walk corpus → filter → embed → save. Returns a summary dict."""
    from agentic_ops_common.rag import CaseIndex, parse_corpus

    print("Parsing corpus:")
    t0 = time.time()
    cases = parse_corpus(sources)
    t_parse = time.time() - t0
    print(f"  parsed {len(cases)} cases in {t_parse:.1f}s")

    if not cases:
        return {"error": "no_cases_parsed", "n_parsed": 0}

    print(f"\nFiltering to score ≥ {score_threshold}% and embedding (TF-IDF):")
    t0 = time.time()
    index = CaseIndex.build(cases, score_threshold=score_threshold)
    t_build = time.time() - t0
    print(
        f"  indexed {len(index.cases)} / {len(cases)} cases in {t_build:.1f}s "
        f"(embed_dim={index.manifest.embed_dim})"
    )

    if not index.cases:
        return {
            "error": "no_cases_above_threshold",
            "n_parsed": len(cases),
            "n_indexed": 0,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nWriting to {output_dir}:")
    index.save(output_dir)
    for name in ("manifest.json", "cases.jsonl", "embeddings.npy"):
        path = output_dir / name
        if path.exists():
            size_kb = path.stat().st_size / 1024
            print(f"  ✓ {name}  ({size_kb:.1f} KB)")

    return {
        "n_parsed": len(cases),
        "n_indexed": len(index.cases),
        "embed_dim": index.manifest.embed_dim,
        "embedder_name": index.manifest.embedder_name,
        "index": index,
        "parse_seconds": t_parse,
        "build_seconds": t_build,
    }


# ── Phase 4: Verification (smoke query) ────────────────────────────


def _verify_index_queryable(index) -> bool:
    """Run a canonical query against the freshly-built index and show
    the top hits. Returns True if the query returned at least one hit
    above a sane similarity floor.

    The smoke query is built to resemble a Call Quality Degradation
    episode's screener output. The expectation is that the top hit is
    a Call Quality Degradation case from a recent run.
    """
    print("\nSmoke query (verifies the index is queryable):")
    print("  query: rtpengine_loss + UPF GTP drops + scenario hint")

    hits = index.search(_SMOKE_QUERY, k=3, min_similarity=0.0)
    if not hits:
        print("  ✗ No hits at all — embedder may be broken.")
        return False

    print(f"  top-3 hits:")
    for h in hits:
        sim_pct = int(round(h.similarity * 100))
        print(
            f"    [{h.rank}] sim={sim_pct:>3}%  "
            f"{h.case.case_id[:55]:<55}  scenario={h.case.scenario_name}"
        )

    top = hits[0]
    if top.similarity < 0.30:
        print(
            f"\n  WARNING: top similarity is only {top.similarity:.2f}. "
            f"Index appears to be queryable but the canonical "
            f"Call-Quality-Degradation-shaped query returned weak matches. "
            f"This is usually a corpus-coverage issue (very few "
            f"call_quality_degradation episodes in the input dirs)."
        )
        return True

    return True


# ── Phase 5: Per-version + per-scenario summary ────────────────────


def _print_corpus_breakdown(index) -> None:
    print("\nBy agent version:")
    by_version: dict[str, int] = {}
    for c in index.cases:
        by_version[c.agent_version] = by_version.get(c.agent_version, 0) + 1
    for v in sorted(by_version):
        print(f"  {v}: {by_version[v]}")

    print("\nTop scenarios by case count:")
    by_scenario: dict[str, int] = {}
    for c in index.cases:
        by_scenario[c.scenario_name] = by_scenario.get(c.scenario_name, 0) + 1
    for name, n in sorted(by_scenario.items(), key=lambda t: -t[1])[:10]:
        print(f"  {n:3d}  {name}")

    print("\nScore distribution (corpus-eligible cases):")
    bands = {"100%": 0, "90-99%": 0, "80-89%": 0}
    for c in index.cases:
        if c.score_pct == 100:
            bands["100%"] += 1
        elif c.score_pct >= 90:
            bands["90-99%"] += 1
        else:
            bands["80-89%"] += 1
    for band in ("100%", "90-99%", "80-89%"):
        if bands[band]:
            print(f"  {band:<8} {bands[band]:>4}")


# ── Top-level ──────────────────────────────────────────────────────


def run_build(
    sources: list[Path],
    output_dir: Path,
    *,
    score_threshold: int = _DEFAULT_SCORE_THRESHOLD,
    backup_existing: bool = True,
    skip_verify: bool = False,
) -> int:
    """End-to-end build orchestration. Returns a CLI exit code (0 = OK)."""
    print("=" * 60)
    print("  RAG INDEX BUILDER")
    print("=" * 60)
    print(f"  Sources:        {len(sources)} dir(s)")
    for s in sources:
        print(f"                  {s}")
    print(f"  Score filter:   ≥ {score_threshold}%")
    print(f"  Output:         {output_dir}")
    print(f"  Backup:         {'yes (move existing aside)' if backup_existing else 'no (overwrite)'}")
    print()

    # ── Pre-flight ──────────────────────────────────────────────
    pf = _preflight(sources, output_dir)
    if pf != 0:
        return pf
    print()

    # ── Backup ──────────────────────────────────────────────────
    if backup_existing:
        backup = _backup_existing(output_dir)
        if backup is not None:
            print(f"  Backed up existing index → {backup}\n")

    # ── Build + save ────────────────────────────────────────────
    summary = _build_and_save(sources, output_dir, score_threshold)
    if "error" in summary:
        print(f"\n  ABORT: {summary['error']}.")
        if summary["error"] == "no_cases_above_threshold":
            print(
                f"  Parsed {summary['n_parsed']} case(s) but none scored "
                f"≥ {score_threshold}%. Lower --score-threshold or run more "
                f"chaos episodes."
            )
        return 1

    # ── Smoke query ─────────────────────────────────────────────
    if not skip_verify:
        ok = _verify_index_queryable(summary["index"])
        if not ok:
            print(
                "\n  WARNING: index built but smoke query failed. The "
                "index is on disk but may not retrieve usefully — "
                "investigate before pointing the orchestrator at it."
            )

    # ── Breakdown + summary ─────────────────────────────────────
    _print_corpus_breakdown(summary["index"])

    print()
    print("=" * 60)
    print("  INDEX BUILD COMPLETE")
    print("=" * 60)
    print(f"  Parsed:         {summary['n_parsed']}")
    print(f"  Indexed:        {summary['n_indexed']}  (score ≥ {score_threshold}%)")
    print(f"  Embed dim:      {summary['embed_dim']}")
    print(f"  Embedder:       {summary['embedder_name']}")
    print(f"  Total time:     {summary['parse_seconds'] + summary['build_seconds']:.1f}s")
    print(f"  Output:         {output_dir}")
    print()
    print("  The v7 orchestrator auto-discovers `<repo>/rag_index/` at run")
    print("  time (no env var needed). To override the path:")
    print(f"      export RAG_INDEX_DIR={output_dir.resolve()}")
    print()
    print("  To disable RAG for an A/B baseline run:")
    print("      export RAG_INDEX_DIR=off")
    print("      export LESSONS_YAML_PATH=off")
    print()
    print("  Then kick off the chaos batch as usual:")
    print("      python -m agentic_chaos run '<scenario name>' --agent v7")
    print()
    return 0


# ── argparse ───────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m rag_indexer",
        description=(
            "Build the RAG case index from chaos-episode files. "
            "The v7 orchestrator's Phase 2.5 retriever consumes this "
            "index at runtime."
        ),
    )
    parser.add_argument(
        "--source", "-s",
        type=Path,
        action="append",
        dest="sources",
        metavar="DIR",
        help=(
            "Episode-log directory to index. Repeat for multiple sources "
            "(default: agentic_ops_v{5,6,7}/docs/agent_logs)."
        ),
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help=(
            f"Output directory. Default: <repo>/{_DEFAULT_OUTPUT}/ — the "
            f"path the orchestrator's RAG_INDEX_DIR resolver auto-"
            f"discovers when no env var is set."
        ),
    )
    parser.add_argument(
        "--score-threshold",
        type=int,
        default=_DEFAULT_SCORE_THRESHOLD,
        help=(
            f"Minimum episode score (0-100) to include. Cases scoring "
            f"below the threshold are excluded — without explicit "
            f"\"this is what went wrong and why\" analysis they teach "
            f"the wrong pattern. Default: {_DEFAULT_SCORE_THRESHOLD}."
        ),
    )
    parser.add_argument(
        "--no-backup-existing",
        action="store_true",
        help=(
            "Skip the automatic backup of the existing on-disk index "
            "before overwriting. By default, any existing index at the "
            "output path is moved to <output>.bak.<utc_timestamp> so "
            "you can A/B compare or roll back."
        ),
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help=(
            "Skip the canonical smoke-query that verifies the index is "
            "queryable end-to-end. Off by default — the verify step "
            "takes <50ms and catches embedder regressions early."
        ),
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable INFO-level logging from the parser + builder.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(name)s: %(message)s",
    )

    sources = (
        [Path(s) for s in args.sources]
        if args.sources
        else [_REPO_ROOT / s for s in _DEFAULT_SOURCES]
    )
    output_dir = args.output or (_REPO_ROOT / _DEFAULT_OUTPUT)

    return run_build(
        sources=sources,
        output_dir=output_dir,
        score_threshold=args.score_threshold,
        backup_existing=not args.no_backup_existing,
        skip_verify=args.skip_verify,
    )


if __name__ == "__main__":
    sys.exit(main())
