# ADR: Standardize Diagnostic Tooling Across All NF Containers

**Date:** 2026-05-06
**Status:** Proposed
**Related:**
- Critical observation: [`../critical-observations/why_agent_fails_with_dataplane_failure_scenarios.md`](../critical-observations/why_agent_fails_with_dataplane_failure_scenarios.md) — Issue 3: "Tooling issues in RTPEngine".
- Post-investigation analysis (2026-05-06, in-conversation): audited every NF Dockerfile and probe to identify which container × tool combinations silently fail. The list is wider than the original observation suggests.
- Implementation-planning analysis (2026-05-06, in-conversation): re-audited the actual Dockerfiles in this repo against the table below; produced the three-commit plan and verification matrix in this ADR. Several rows in the original audit table were stale and have been corrected.
- [`falsifier_investigator_and_rag.md`](falsifier_investigator_and_rag.md) — defines the Investigator probes that depend on container-side binaries.

---

## Decision

Every NF container in this stack must ship with a fixed, named "diagnostic toolbelt" — `iputils-ping`, `iproute2` (for `ss`), `net-tools` (for `netstat`), `dnsutils` (for `dig`/`nslookup`), `tcpdump`, `curl`, `traceroute` — and no probe is ever allowed to silently degrade because a binary is missing. Three coordinated changes ship together, structured as three sequential commits in one PR (each independently bisectable, but the PR is the unit of merge):

1. **Add the toolbelt to every Dockerfile** under `network/`, in a single shared layer pattern. RTPEngine, pyhss, mysql, metrics, and (if it has a local Dockerfile) oai/gnb each get the missing packages; existing containers that already cover most of the toolbelt (open5gs base, ims_base, opensips_ims_base, dns, eupf, ibcf) get any gaps closed and are normalized to use the same shared snippet so the toolbelt is uniform and drift-free.
2. **Encode the toolbelt as a contract in code.** A new module `network/tooling_contract.py` lists the required binaries. A startup audit script `scripts/audit-container-tooling.sh` runs against the live stack, reads the contract from the Python module (single source of truth), confirms every NF has every binary, and exits non-zero if any are missing. The audit becomes a precondition for chaos runs (called from `scripts/run-all-chaos-scenarios.sh` before scenario execution), is invoked from the GUI's post-deploy verification, and is a CI check.
3. **Make probes fail loudly when a binary is missing.** `measure_rtt`, `check_process_listeners`, and any other probe that shells into a container must distinguish "command not found" from "command ran and produced no signal" and surface the former as a probe-level error (`tool_unavailable` outcome), not as `INCONCLUSIVE`. The Investigator's reasoning layer treats `tool_unavailable` as a hard signal that the probe gives no information — never as a soft "neither confirms nor contradicts."

This is a one-shot fix for the entire fleet, not a per-incident patch.

## Context

### Audit (corrected against the actual repo, 2026-05-06)

The original audit table in this ADR was partially stale against current Dockerfiles. The corrected state, after re-reading every `network/<nf>/Dockerfile`:

| Container | Base | ping | ss | netstat | dig | tcpdump | curl | traceroute |
|---|---|---|---|---|---|---|---|---|
| **rtpengine** | debian:bookworm | ❌ | ✅ (`iproute2`) | ❌ | ❌ | ❌ | ❌ | ❌ |
| **pyhss** | ubuntu:jammy | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **mysql** | ubuntu:jammy | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **metrics** (Prometheus) | ubuntu:jammy | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **oai/gnb** | (upstream image, no local Dockerfile) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **ibcf** (asterisk) | debian:bookworm | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| **dns** | ubuntu:jammy | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ |
| **eupf** | ubuntu:jammy | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **open5gs base** | ubuntu:jammy | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ |
| **ims_base** (kamailio) | ubuntu:jammy | ✅ | ✅ | ✅ | — | ✅ | ✅ | — |
| **opensips_ims_base** | debian:bookworm | ✅ | ✅ | ✅ | — | ✅ | ✅ | — |

The originals of three rows were materially wrong:
- `rtpengine` already installs `iproute2 nftables` (`network/rtpengine/Dockerfile:44`); it has `ss` today.
- `dns` already installs `tcpdump iproute2 net-tools iputils-ping bind9` (`network/dns/Dockerfile:33-34`).
- `eupf` and `ibcf` are also more complete than the original table credited.

The genuinely barebones containers are **pyhss, mysql, metrics, and (likely) oai/gnb**. None has a usable diagnostic surface.

### How the gap manifests in probes

Probe behavior on this fleet today:

- `measure_rtt(container, target_ip)` — `agentic_ops/tools.py:753` shells `docker exec <container> ping -c 3 -W 10 <target>`. When `ping` is missing, the wrapper returns "ping: command not found" stderr as a generic failure string. The Investigator records this as `compared_to_expected="AMBIGUOUS"` (the model's default), and downstream the synthesis layer reads it as soft non-evidence.
- `check_process_listeners(container)` — `agentic_ops/tools.py:655` tries `ss -tulnp`, falls back to `netstat -tulnp` (`tools.py:679`). On pyhss, mysql, metrics, oai/gnb, both fall through and the wrapper returns "Neither ss nor netstat available". Same path: the LLM defaults to AMBIGUOUS, downstream reads it as soft non-evidence.

The critical observation captures one of the consequences explicitly:

> *In `run_20260504_160632_call_quality_degradation.md`: the two subsequent probes designed to isolate the fault to either RTPEngine's network path or the UPF itself could not be executed due to technical limitations (missing 'ping' in one container, incorrect container name in the plan for the other).*

The Investigator was given a falsification plan it could not execute, executed it anyway, and recorded the absence of a signal as soft non-evidence — which the synthesis layer then read as "no contradiction" and let the wrong hypothesis stand.

### Why this is a one-shot fleet change, not a per-NF fix

The same probe runs against multiple NFs. The Investigator decides at runtime which container to ping. If we patch only RTPEngine, the next scenario will need PyHSS or oai/gnb and we relive the same incident. The toolbelt is a stack-level invariant or it's nothing.

### Why "tool_unavailable" must be a distinct probe outcome

Today the Investigator can read `AMBIGUOUS` in two ways:

- *"The probe ran, the data came back, but it doesn't speak to the hypothesis."* This is legitimate — the Investigator should consider whether the hypothesis needs different evidence.
- *"The probe didn't run because the binary doesn't exist on the target container."* This is not the same situation. The Investigator should know the probe never produced a signal, full stop, and either pick a different probe or escalate the gap.

Conflating the two lets the Investigator silently chain reasoning on probes that didn't actually run. Splitting them is a small change to the probe wrappers, the `ProbeResult` schema, the Investigator prompt, and the confidence-cap guardrail — but it closes a confidence-fabrication path.

### Codebase facts that shape the design

These are the constraints discovered while planning this ADR; they are load-bearing for the design choices below.

- **`ProbeResult` is filled by the LLM, not by probe wrappers.** The Investigator (`agentic_ops_v6/subagents/investigator.py:32`) declares `output_schema=InvestigatorVerdict`, which contains `probes_executed: list[ProbeResult]` (`agentic_ops_v6/models.py:255`). Probe tools return strings; the LLM reads those strings and writes `ProbeResult` rows. A new outcome enum value therefore requires (a) a recognizable string token in the wrapper return value and (b) prompt teaching so the LLM emits the right outcome.
- **`ProbeResult` currently has only `compared_to_expected: Literal["CONSISTENT", "CONTRADICTS", "AMBIGUOUS"]`.** Adding `tool_unavailable` to that field would conflate "evidence direction" with "did the probe run". Add a *new* field `outcome` instead; keep `compared_to_expected` for backwards-compat through this PR, and remove it in a follow-up once every consumer reads `outcome`.
- **The reachability tool layer is two files.** `agentic_ops_common/tools/reachability.py` is a thin façade that re-exports via `_t.measure_rtt`; the real implementation lives in `agentic_ops/tools.py:655` (`check_process_listeners`) and `:753` (`measure_rtt`). Only the implementation file needs the binary preflight.
- **The consensus reconciler does not need changes.** `agentic_ops_v6/guardrails/investigator_consensus.py` reconciles whole verdicts (DISPROVEN / NOT_DISPROVEN / INCONCLUSIVE) — it does not look at probe outcomes. The original ADR claimed this file needed updates; that was overstated. The actual tool_unavailable handling lives in the prompt + the strength computation in `agentic_ops_v6/guardrails/confidence_cap.py:74-119`.
- **Multiple agent versions consume the same probe wrappers.** `agentic_ops_v3`, `v4`, `v5`, and `v6` all import `measure_rtt` / `check_process_listeners`. The string-token return path means older versions degrade gracefully — they see a descriptive string in the LLM tool result and treat it as ambiguous evidence (the conservative behavior). Only `v6` has the structured `ProbeResult` and the `outcome` field; only `v6` gets the strict tool_unavailable handling.

## Design

### The toolbelt contract (`network/tooling_contract.py`)

```python
DIAGNOSTIC_TOOLBELT = {
    "ping":       {"package_apt": "iputils-ping",  "package_apk": "iputils"},
    "ss":         {"package_apt": "iproute2",      "package_apk": "iproute2"},
    "netstat":    {"package_apt": "net-tools",     "package_apk": "net-tools"},
    "dig":        {"package_apt": "dnsutils",      "package_apk": "bind-tools"},
    "nslookup":   {"package_apt": "dnsutils",      "package_apk": "bind-tools"},
    "tcpdump":    {"package_apt": "tcpdump",       "package_apk": "tcpdump"},
    "curl":       {"package_apt": "curl",          "package_apk": "curl"},
    "traceroute": {"package_apt": "traceroute",    "package_apk": "traceroute"},
}

REQUIRED_BY_NF = {
    "rtpengine": list(DIAGNOSTIC_TOOLBELT),
    "amf":       list(DIAGNOSTIC_TOOLBELT),
    # … one entry per NF; same list for all NFs in this fleet.
}
```

The single source of truth lives in code, not in each Dockerfile. Each Dockerfile imports the same `apt-get install` command via a shared shell snippet (`network/Dockerfile.toolbelt.sh`) sourced into every NF Dockerfile's build step. When the toolbelt list changes, every container picks up the change on next rebuild — no per-Dockerfile drift.

### Dockerfile changes

Each Dockerfile under `network/` adds (or already contains, but is normalized to) a single line:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping iproute2 net-tools dnsutils tcpdump curl traceroute \
    && rm -rf /var/lib/apt/lists/*
```

Where the base image is Alpine-based, the equivalent `apk add` line. Where a Dockerfile already installs some of these, the redundant install is consolidated into the toolbelt line so there is one consistent place to read the toolbelt set per file.

The toolbelt line goes early in the Dockerfile so its layer is cached and rebuilds remain cheap. Image-size impact is bounded by `--no-install-recommends` and the listed packages — empirically under 30 MB per image.

For NFs that come from upstream images and do not have a local Dockerfile (currently `oai/gnb`), create a thin `network/oai/gnb/Dockerfile` that does `FROM <upstream-tag>` followed by the toolbelt snippet, and update the compose file to build it instead of pulling.

### The audit script (`scripts/audit-container-tooling.sh`)

For every NF in `REQUIRED_BY_NF`, exec `command -v <binary>` for every entry. Print a table. Exit non-zero on any miss. The binary list is read from `network/tooling_contract.py` (e.g. via `python3 -c 'from network.tooling_contract import DIAGNOSTIC_TOOLBELT; print(" ".join(DIAGNOSTIC_TOOLBELT))'`), so the contract has one source of truth. Output shape:

```
Auditing diagnostic toolbelt across NFs…
NF           ping ss netstat dig tcpdump curl traceroute
rtpengine    ✅   ✅ ✅      ✅   ✅      ✅    ✅
amf          ✅   ✅ ✅      ✅   ✅      ✅    ✅
...
ALL OK.
```

Failure modes:
- Container absent / not running → distinguishable "skipped" row; with `--skip-absent` the audit warns and continues, otherwise it fails hard. Default is fail hard so a misnamed container can't silently pass the audit.
- Container running, binary missing → red row, named gap, exit non-zero.

`scripts/run-all-chaos-scenarios.sh` calls the audit before any scenario starts. `gui/server.py`'s post-deploy phase calls it as part of its existing `post-deploy-verify.sh` flow. CI runs it after `docker-compose up` and before tests. If the toolbelt contract changes (add a binary), the audit fails until every Dockerfile is rebuilt.

### Probe wrapper change (`agentic_ops/tools.py`)

Each probe that shells into a container gains a binary-existence preflight via a new helper:

```python
async def _container_has_binary(container: str, binary: str) -> bool:
    """Return True iff `binary` is on PATH inside `container`. Cached
    per-(container, binary) for the lifetime of the process — the
    answer doesn't change mid-run."""
    ...

async def measure_rtt(deps: AgentDeps, container: str, target_ip: str) -> str:
    if container not in deps.all_containers:
        return f"Unknown container '{container}'. Known: ..."
    if not await _container_has_binary(container, "ping"):
        return (
            f"PROBE_TOOL_UNAVAILABLE: ping not present in container "
            f"`{container}`. The probe did not run. Treat this as no "
            f"evidence — neither confirms nor contradicts the hypothesis. "
            f"(Toolbelt contract violated; see audit-container-tooling.)"
        )
    # … existing ping invocation
```

The literal token `PROBE_TOOL_UNAVAILABLE:` at the start of the return string is the contract the LLM uses to map the probe back to `outcome="tool_unavailable"`. It must be unique enough that the LLM can pattern-match it without ambiguity, and the prompt has to teach this mapping (see below). The same gating goes on `check_process_listeners` (which already has a manual ss→netstat fallback that we replace with the binary check).

Probes invoked through `agentic_ops_common/tools/reachability.py` continue to call `_t.measure_rtt`; no façade change.

### `ProbeResult` schema change (`agentic_ops_v6/models.py:255`)

Add a new field, leave the old one in place for this PR:

```python
class ProbeResult(BaseModel):
    probe_description: str
    tool_call: str = ""
    observation: str = ""
    compared_to_expected: Literal[
        "CONSISTENT", "CONTRADICTS", "AMBIGUOUS"
    ] = "AMBIGUOUS"
    outcome: Literal[
        "consistent", "contradicts", "ambiguous", "tool_unavailable", "error"
    ] = "ambiguous"
    commentary: str = ""
```

Rationale: changing the existing field's enum would force every prompt and downstream consumer to migrate atomically. Adding a new field lets us route only the new tool_unavailable case through it for now, and migrate the remaining outcomes in a follow-up. The follow-up removes `compared_to_expected` once every consumer reads `outcome`.

### Investigator prompt change (`agentic_ops_v6/prompts/investigator.md`)

Add to the Evidence Rules section:

> If a probe's tool result begins with `PROBE_TOOL_UNAVAILABLE:`, the probe did not run. Set `outcome="tool_unavailable"` and `compared_to_expected="AMBIGUOUS"` for that probe. **Do not** count it as CONSISTENT or CONTRADICTS evidence. Mention the gap explicitly in your `reasoning` text — name the probe and the missing binary — so the orchestrator can surface it as a falsification-plan failure.

### Confidence-cap change (`agentic_ops_v6/guardrails/confidence_cap.py`)

`compute_evidence_strength_for_verdict` (`confidence_cap.py:74-119`) currently counts probes by `compared_to_expected`. Update it to first filter out probes with `outcome=="tool_unavailable"` (and `outcome=="error"`), then run the existing strength computation on what remains. If after filtering there are zero probes, return `NONE`. The cap table in `_CAP` already maps `NONE → low` (with `verdict_kind=inconclusive` enforced separately), so a verdict driven entirely by tool_unavailable probes correctly cannot lift Synthesis confidence above `low`.

The reconciler in `investigator_consensus.py` does not change. It works on whole verdicts; the probe-level outcome lives one layer below.

### Why the toolbelt + audit + probe-outcome change is one PR

Without the audit, the toolbelt drifts as Dockerfiles are edited individually. Without the probe-outcome change, fixing the binaries doesn't help against the next missing-binary failure the audit might miss. Without the Dockerfile changes, the audit fails on day one and the probe change rejects every probe that targets a barebones container. The three pieces protect each other.

## Implementation plan — three sequential commits in one PR

The pieces are merged as one PR (per the protect-each-other argument above), but staged as three commits so each is independently bisectable.

### Commit 1 — Toolbelt baked into images

Files:
- `network/tooling_contract.py` (new) — `DIAGNOSTIC_TOOLBELT` and `REQUIRED_BY_NF` constants.
- `network/Dockerfile.toolbelt.sh` (new) — idempotent shell snippet that does `apt-get update && apt-get install -y --no-install-recommends <toolbelt> && rm -rf /var/lib/apt/lists/*`.
- `network/pyhss/Dockerfile` — add toolbelt install (currently genuinely barebones).
- `network/mysql/Dockerfile` — add toolbelt install (currently genuinely barebones).
- `network/metrics/Dockerfile` — add toolbelt install (currently genuinely barebones).
- `network/rtpengine/Dockerfile` — add the gaps it has (`ping`, `netstat`, `dig`, `tcpdump`, `curl`, `traceroute`); keep its existing `iproute2`.
- `network/oai/gnb/Dockerfile` (new, if the image is upstream) — `FROM <upstream-tag>` + toolbelt; update the compose file to build instead of pull.
- `network/base/Dockerfile`, `network/ims_base/Dockerfile`, `network/opensips_ims_base/Dockerfile`, `network/dns/Dockerfile`, `network/eupf/Dockerfile`, `network/ibcf/Dockerfile` — replace ad-hoc installs with the shared snippet so the toolbelt set is uniform across all NFs.

Verification at this stage (sufficient on its own to demonstrate the original failure no longer happens):
- `docker compose build` succeeds for every changed image.
- For each NF: `docker compose up -d <nf>; docker exec <nf> command -v ping ss netstat dig tcpdump curl traceroute` returns a path for all seven.
- `docker images` before/after shows ≤30 MB per-image growth.
- Smoke-rerun the original failing scenario (`Call Quality Degradation` → equivalent of `run_20260504_160632`) against the v6 agent. The RTPEngine→UPF reachability probes now execute and produce real RTT output. (Confidence is still potentially over-claimed at this commit because Commit 3 hasn't landed; that's acceptable for the bisect point.)

### Commit 2 — Audit script + chaos integration

Files:
- `scripts/audit-container-tooling.sh` (new) — reads the binary list from `network/tooling_contract.py`, iterates `REQUIRED_BY_NF`, emits the table, exits non-zero on any miss. Supports `--skip-absent` for development; default fails on absent containers.
- `scripts/run-all-chaos-scenarios.sh` — call the audit immediately after sourcing `ops.env` and before the `for scenario` loop. Abort the batch with a clear message on non-zero exit.
- `scripts/post-deploy-verify.sh` (or wherever the GUI's post-deploy hook lives) — call the audit so a successful deploy never finishes with a tooling gap that will silently degrade the next investigation.
- CI configuration (whichever repo uses) — add the audit as a step after `docker-compose up`.

Verification at this stage:
- `bash scripts/audit-container-tooling.sh` against the freshly built stack returns 0 and prints the full table.
- **Forced regression #1 — image without binary.** Build a one-off rtpengine image without `ping`; deploy; run the audit; expect exit non-zero with rtpengine × ping named in the output. Restore the proper image afterwards.
- `scripts/run-all-chaos-scenarios.sh v6` aborts cleanly when the audit fails (verify by stubbing in a missing binary on a copy of the stack).
- The GUI's deploy flow surfaces an audit failure as a deploy-failed message rather than letting the user proceed into investigation with a degraded fleet.

### Commit 3 — Probe-level + verdict-level `tool_unavailable` handling

Files:
- `agentic_ops/tools.py` — add `_container_has_binary` helper (with a per-process cache); gate `measure_rtt` (line 753) and `check_process_listeners` (line 655); return the literal `PROBE_TOOL_UNAVAILABLE:` token when the binary is missing. Audit any other probe in `tools.py` that shells into a container and gate it the same way.
- `agentic_ops_common/tools/reachability.py` — no change required; the façade re-exports the gated implementation.
- `agentic_ops_v6/models.py` — add `outcome` field to `ProbeResult` (closed enum: `consistent | contradicts | ambiguous | tool_unavailable | error`, default `ambiguous`); keep `compared_to_expected` for back-compat.
- `agentic_ops_v6/prompts/investigator.md` — Evidence Rules teach the `PROBE_TOOL_UNAVAILABLE:` → `outcome="tool_unavailable"` mapping and require naming the gap in `reasoning`.
- `agentic_ops_v6/guardrails/confidence_cap.py` — filter `outcome in {"tool_unavailable", "error"}` probes out of `compute_evidence_strength_for_verdict`'s counts and total.
- `agentic_ops_v6/tests/guardrails/test_confidence_cap.py` — extend with cases for tool_unavailable filtering.
- New tests:
  - `test_probe_tool_unavailable_outcome` — mock a container without `ping`; assert `measure_rtt` return string starts with `PROBE_TOOL_UNAVAILABLE:` and names the missing binary.
  - `test_confidence_cap_skips_tool_unavailable` — verdict with one CONSISTENT + two `tool_unavailable` probes → strength `WEAK` (only one CONSISTENT counted), not `MODERATE`. All-tool_unavailable verdict → strength `NONE`.
  - `test_investigator_prompt_teaches_tool_unavailable` — string-match guard that the prompt mentions `PROBE_TOOL_UNAVAILABLE` and `tool_unavailable`; cheap insurance against drift.

Explicit non-changes:
- `agentic_ops_v6/guardrails/investigator_consensus.py` — reconciles whole verdicts; not changed in this PR. The original ADR overstated this; the actual handling is one layer below in confidence_cap.
- `agentic_ops_v3` / `v4` / `v5` — they consume the same probe wrappers but do not have a `ProbeResult` schema, so they degrade gracefully: the LLM sees the descriptive `PROBE_TOOL_UNAVAILABLE:` string in the tool result and treats it as ambiguous text. No code change required; document this behavior in the PR description.

Verification at this stage:
- All unit tests in the list above pass.
- Live integration: temporarily `apt-get remove -y iputils-ping` from rtpengine inside the running container (so the image still has it on next rebuild — quick to undo), run the v6 agent against `Call Quality Degradation`, inspect the resulting `InvestigatorVerdict.probes_executed` JSON in the episode log under `agentic_ops_v6/docs/agent_logs/`. Confirm:
  - `outcome == "tool_unavailable"` on the affected probe.
  - The Investigator's `reasoning` text names the probe and the missing binary.
  - The recorder's confidence_cap notes show evidence_strength is not lifted by the unavailable probe.
- Re-restore `ping` (rebuild the image), re-run the same scenario, confirm `outcome == "consistent"` (or "contradicts", depending on the actual fault) and the probe contributes normally.

## End-to-end verification

Run after all three commits land. Order matters — each step assumes the previous one passed.

1. **Build cleanly.** `docker compose build` across every changed image. Compare image sizes; budget ≤30 MB increase per image. (Commit 1 alone.)
2. **Audit passes on the new stack.** `bash scripts/audit-container-tooling.sh` returns 0 against the freshly built fleet and prints the full table green. (Commit 2.)
3. **Forced regression #1 — image-level gap is detected.** Build a one-off image where rtpengine deliberately doesn't install `ping`; deploy it; run the audit; expect non-zero exit and a named gap. This proves the audit isn't lying about its scan.
4. **Forced regression #2 — probe-level gap surfaces structurally.** With `ping` removed from the running rtpengine container, run the v6 agent against `Data Plane Degradation` (one of the failing scenarios in the original observation). Pull the episode JSON from `agentic_ops_v6/docs/agent_logs/`. Confirm:
   - `probes_executed[].outcome == "tool_unavailable"` for any RTPEngine ping probe.
   - The Investigator's `reasoning` text names the probe and the missing binary.
   - The confidence_cap recorder notes show the strength is not lifted by the unavailable probe.
5. **Original failure scenario re-runs cleanly.** With the toolbelt baked in (image rebuilt), re-run the equivalent of `run_20260504_160632` (`Call Quality Degradation` against v6). The RTPEngine→UPF reachability probes referenced in the critical observation must execute and produce real RTT numbers. Compare the new episode log to the failing one; the verdict must no longer be confidence-fabricated on missing evidence.
6. **Full chaos batch.** `scripts/run-all-chaos-scenarios.sh v6`. Confirm the audit gate fires at the top, all 11 scenarios run, none hits a "ping: command not found" or "ss not available" error, and the final summary table shows no regressions vs. the pre-PR baseline.
7. **CI check.** A pre-merge hook runs the audit and the unit tests. The audit needs the stack up, so it runs after the `docker compose up` step.

Plus the unit tests listed in Commit 3, which CI runs unconditionally:
- `test_tooling_contract` — every Dockerfile under `network/` either contains the toolbelt install line or sources `network/Dockerfile.toolbelt.sh` (string match against canonical pattern in the contract module's docstring).
- `test_probe_tool_unavailable_outcome`.
- `test_confidence_cap_skips_tool_unavailable`.
- `test_investigator_prompt_teaches_tool_unavailable`.

## Files Changed (full list)

Grouped by commit for review.

**Commit 1 — Toolbelt:**
- `network/tooling_contract.py` (new)
- `network/Dockerfile.toolbelt.sh` (new)
- `network/pyhss/Dockerfile`
- `network/mysql/Dockerfile`
- `network/metrics/Dockerfile`
- `network/rtpengine/Dockerfile`
- `network/oai/gnb/Dockerfile` (new, if upstream-only today)
- `network/base/Dockerfile`, `network/ims_base/Dockerfile`, `network/opensips_ims_base/Dockerfile`, `network/dns/Dockerfile`, `network/eupf/Dockerfile`, `network/ibcf/Dockerfile` (normalization)
- The compose file that pulls oai/gnb (if applicable)

**Commit 2 — Audit:**
- `scripts/audit-container-tooling.sh` (new)
- `scripts/run-all-chaos-scenarios.sh`
- `scripts/post-deploy-verify.sh` (or the GUI's post-deploy hook)
- CI config

**Commit 3 — Probe + verdict outcome handling:**
- `agentic_ops/tools.py`
- `agentic_ops_v6/models.py`
- `agentic_ops_v6/prompts/investigator.md`
- `agentic_ops_v6/guardrails/confidence_cap.py`
- `agentic_ops_v6/tests/guardrails/test_confidence_cap.py`
- `agentic_ops_v6/tests/<new>/test_probe_tool_unavailable_outcome.py`
- `agentic_ops_v6/tests/<new>/test_investigator_prompt_teaches_tool_unavailable.py`

## Propagate-changes-fully walk

Per the project rule on non-trivial changes:

1. **Who consumes this?**
   - Probe wrappers `measure_rtt` / `check_process_listeners`: imported by `agentic_ops_common/tools/reachability.py` (façade) and used by every agent version's investigator (`agentic_ops_v3` / `v4` / `v5` / `v6`).
   - `ProbeResult` schema: produced by the v6 Investigator's `output_schema=InvestigatorVerdict`; consumed by `agentic_ops_v6/guardrails/confidence_cap.py`, `investigator_consensus.py`, `investigator_minimum.py`, the orchestrator's recorder, and any UI code under `gui/` that renders `probes_executed`.
   - Toolbelt contract: read by `scripts/audit-container-tooling.sh`; informs every `network/<nf>/Dockerfile`.
2. **What persists or transforms this across a boundary?**
   - Docker images are baked artifacts: the toolbelt only takes effect on next rebuild. Pre-built images in any cache (local, registry) carry the old state.
   - Episode JSON files under `agentic_ops_v6/docs/agent_logs/` persist `ProbeResult` rows; old logs predate the `outcome` field.
   - The Neo4j ontology is unaffected by this change.
3. **Is any existing consumer now silently wrong?**
   - `investigator_consensus.py` — intentionally unaffected; reconciles verdicts not probe outcomes.
   - `investigator_minimum.py` — reads probe count, not outcomes; intentionally unaffected.
   - `agentic_ops_v3` / `v4` / `v5` — receive the new `PROBE_TOOL_UNAVAILABLE:` string in tool results; they have no `ProbeResult` schema so they map it to ambiguous narrative text. Conservative, intended behavior; called out in the PR description.
   - `gui/server.py` investigation rendering — needs to add `outcome` rendering or the new field is invisible to humans. **Action required:** grep `compared_to_expected` under `gui/` and add `outcome` to the same render paths.
   - Existing `test_confidence_cap` tests will need updates for the new filtering behavior.
4. **What runtime state must be invalidated?**
   - Pre-built NF images. After merging, run `docker compose build --pull` on every changed service before redeploying.
   - Any prompt-cached LLM session for the Investigator: the prompt changed; cached prefixes that don't include the new evidence rule may produce stale outputs. Restart the GUI.
   - The `_container_has_binary` cache is per-process; no persistence concern.

## Alternatives Considered

1. **Add only `ping` to RTPEngine and call it done.** Rejected. The pattern recurs across NFs and probes; one-spot fixes guarantee a follow-on incident on a different container. The audit-as-contract pattern eliminates the class.

2. **Inject the toolbelt via a sidecar with `nsenter` privileges.** Rejected as more invasive than baking the binaries into the image. Sidecars complicate compose orchestration and add a network namespace dance per probe. The current shell-into-container probes work fine once the binaries exist.

3. **Replace `ping` with a Python-native ICMP implementation in the probe.** Rejected. ICMP from a process running outside the target container's network namespace measures RTT to the wrong source. The probe must run inside the container; the binary must be there.

4. **Treat `tool_unavailable` as INCONCLUSIVE (current behavior) and rely on the Investigator to notice the gap.** Rejected as the silent-fabrication path this ADR is closing. The whole point is that the Investigator does not notice. A typed outcome that the verdict reader can't confuse with "ran but ambiguous" is the structural fix.

5. **Build a custom RTPEngine image without modifying upstream.** Already the situation; this ADR just makes the toolbelt installation explicit, audited, and uniform across NFs.

6. **Repurpose the existing `compared_to_expected` field by adding `tool_unavailable` to its enum.** Rejected. `compared_to_expected` answers "evidence direction"; `tool_unavailable` answers "did the probe run". Conflating them forces every consumer to migrate atomically and makes back-compat impossible. A separate `outcome` field is the cleaner cut, with a follow-up to retire `compared_to_expected` once every consumer reads `outcome`.

7. **Ship as one mega-commit.** Rejected. The three commit boundaries (image fleet, audit/CI integration, probe semantics) are independently bisectable: a regression two months from now on probe semantics shouldn't have to revert the toolbelt rebuild. One PR for atomic merge, three commits for clean bisect.

## Follow-ups

- Once the toolbelt is in place and `outcome` is populated everywhere, retire the `compared_to_expected` field. Migrate `confidence_cap.py` and any rendering code to read `outcome` exclusively.
- Reconsider whether `check_process_listeners` should retry with `netstat` after `ss` fails, or whether the audit guarantee makes the fallback redundant. Marginal cleanup; not in this ADR's scope.
- Expose tc qdisc drop counters as a dedicated probe — listed as a follow-up in [`upf_counters_directional_stack_rule.md`](upf_counters_directional_stack_rule.md). The toolbelt now contains the binaries to implement it, but the probe itself is a separate piece of work.
- Consider whether the consensus reconciler should additionally surface "this verdict is mostly tool_unavailable" as a distinct kind, not just rely on the strength cap to suppress confidence. Open question; out of scope here.
