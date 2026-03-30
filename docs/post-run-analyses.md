# Post-Run Analyses — RCA Agent Performance Across Versions

A compilation of all post-run analyses, RCA reflections, and agent performance evaluations across v1.5, v2, v3, and v4 agents.

---

## Score Summary

| Scenario | Agent | Score | Tokens | Time | Root Cause Found? |
|---|---|---|---|---|---|
| UE1→UE2 Call Failure | v1 | 10% | 200K | ~2m | No — blamed I-CSCF Diameter config |
| UE1→UE2 Call Failure | v1.5 | 90% | 159K | ~1.5m | Yes — TCP/UDP mismatch at P-CSCF |
| gNB Kill (Run 1) | v3 | 40% | 190K | 137s | No — "AMF not listening on SCTP" |
| gNB Kill (Run 2) | v3 | ~20% | 100K | — | No — fixated on Diameter I_Open |
| gNB Kill (Run 3) | v3 | 0% | 243K | — | No — hallucinated AMF crash |
| P-CSCF Latency | v3 | 0% | 97K | 94s | No — blamed HSS subscriber profiles |
| HSS Unresponsive | v3 | 100% | 84K | 119s | Yes — PyHSS paused, Diameter down |
| gNB Radio Link Failure | v4 | 0% | 84K | 101s | No — triage correct, specialists wrong |
| Data Plane Degradation (Run 1) | v4 | 0% | 71K | 77s | No — hallucinated S-CSCF port mismatch |
| Data Plane Degradation (Run 2) | v4 | 0% | 81K | 130s | No — blamed pre-existing P-CSCF config |

---

## 1. UE1→UE2 Call Failure — v1 vs v1.5

**Source:** `docs/RCAs/postmortem_ue1_calls_ue2_failure.md`

**Scenario:** UE1 calls UE2. Call fails with "500 Server error on LIR select next S-CSCF" at I-CSCF.

**Actual root cause:** P-CSCF config has `udp_mtu_try_proto = TCP`. INVITE (>1300 bytes with SDP) gets sent to UE2 via TCP, but UE2 only listens on UDP:5060. INVITE silently dropped, timeout cascades back as 500.

### v1 agent (10%)

Diagnosed "I-CSCF missing Diameter client configuration to connect to PyHSS" with high confidence. Completely wrong — Diameter connection was healthy (`I_Open`, all Cx apps registered, 242+ messages/hour).

**Failure mode:** Only verified the originating side of the call. Never traced the INVITE to UE2. Treated the 500 error at the intermediate node as the root cause rather than a symptom.

### v1.5 agent (90%)

After adding `read_running_config` and `check_process_listeners` tools, plus prompt improvements ("check both ends", "metrics first", "SIP INVITE not delivered" pattern), the agent correctly identified the TCP/UDP mismatch.

**Key improvement:** 10% → 90% with 50K fewer tokens (200K → 159K).

**Lessons:**
- Always trace a transaction to BOTH ends
- Absence of evidence IS evidence (INVITE never reached UE2)
- Transport layer settings (UDP vs TCP, MTU) affect SIP delivery
- 500 errors at intermediate nodes are symptoms of upstream failures

---

## 2. gNB Kill — Three v3 Runs

**Source:** `docs/RCAs/gnb_kill_three_runs_analysis.md`

**Scenario:** gNB container killed. All three runs diagnosed incorrectly.

### Run 1 (190K tokens, 40%)

Diagnosed "AMF not listening on SCTP port 38412." Inverted log direction — misread "connection refused" as "we refused their connection." Had `measure_rtt` tool but never used it.

### Run 2 (100K tokens, ~20%)

Diagnosed "metrics inconsistency, Diameter I_Open is the problem." Fixated on pre-existing I_Open condition. Ignored `ran_ue = 0` + `sm_sessionnbr = 4` (classic RAN failure: zero UEs attached, stale sessions). Made 15 RTT measurements between IMS containers but never pinged the gNB IP (172.22.0.23).

### Run 3 (243K tokens, 0%)

Diagnosed "AMF process crashed." Ran `read_running_config("amf", grep="GNB_HOST")` → got nothing → misinterpreted empty output as "config file read failure" (parameter doesn't exist). Burned 170K tokens (70%) reading P-CSCF and I-CSCF logs for stale Call-IDs. Hallucinated technical evidence.

**Pattern across all 3 runs:** Agent never pings the remote endpoint. One `measure_rtt("amf", "172.22.0.23")` call would show 100% packet loss and immediately identify the dead gNB.

**What's hard for agents:**
1. Reading metrics as unreliable rather than interpreting them (`ran_ue = 0` = RAN down)
2. Inverted logic from log messages
3. Knowing WHEN to use tools (diagnostic reflexes)
4. Investigating error sites rather than the failure path
5. Bottom-up methodology — agents are attracted to interesting application-layer errors

---

## 3. P-CSCF Latency — v3

**Source:** `agentic_ops_v3/docs/agent_logs/run_20260325_204757_p_cscf_latency.md`

**Scenario:** 500ms latency injected on P-CSCF container. Score: **0%**.

**Agent diagnosis:** "Incomplete HSS subscriber profiles causing I-CSCF Diameter query failures."

**Actual root cause:** 500ms network latency on P-CSCF causing SIP timeouts.

**Failure mode:** Ignored network latency symptoms entirely. Jumped to an application-layer hypothesis (HSS data) and never checked transport health. Classic top-down failure.

---

## 4. HSS Unresponsive — v3

**Source:** `agentic_ops_v3/docs/agent_logs/run_20260325_221035_hss_unresponsive.md`

**Scenario:** PyHSS container paused. Score: **100%**.

**Agent diagnosis:** "PyHSS container paused, Diameter Cx interface down, all IMS lookups fail." Correct root cause, correct timing, correct affected components.

**Why it worked:** The failure was clean and unambiguous. Container paused → Diameter peer goes down → clear cascading failure visible in metrics and logs. No ambiguity for the agent to get confused by.

**Lesson:** Agents perform well on "hard down" failures with clear metric signatures. They struggle with degradation, latency, and subtle transport issues where symptoms look like application bugs.

---

## 5. gNB Radio Link Failure — v4

**Source:** `agentic_ops_v4/docs/agent_logs/run_20260326_231102_gnb_radio_link_failure.md`

**Scenario:** gNB container killed. Score: **0%**.

**What went right:** The TriageAgent used the new topology tool and immediately saw INACTIVE links at the RAN level. Correctly identified "RAN not connected" in triage output.

**What went wrong:** Downstream specialists ignored the correct triage finding. TransportSpecialist chased pre-existing `httpclient:connfail` noise on P-CSCF. Hallucinated evidence about AMF IP misconfiguration.

**Lesson:** Good input data doesn't guarantee good output. The pipeline can have correct information at the triage phase and still produce a wrong diagnosis if specialists don't respect earlier findings.

---

## 6. Data Plane Degradation — v4 (Two Runs)

**Source:** `agentic_ops_v4/docs/agent_logs/run_20260327_161736_data_plane_degradation.json` and `run_20260327_163009_data_plane_degradation.json`

**Scenario:** 30% packet loss injected on UPF (`tc netem loss 30%`). Both runs scored **0%**.

### Run 1 (71K tokens, 77s)

**Agent diagnosis:** S-CSCF misconfigured to listen on port 6060 instead of 5060 (hallucinated).

**Failure mode:** Only TransportSpecialist was dispatched (plus mandatory inclusion). It had `run_kamcmd` in its toolset, which gave it access to SIP-layer data. Read S-CSCF Kamailio config, misinterpreted the listen port, fabricated a diagnosis.

**Fix applied:** Removed `run_kamcmd` from TransportSpecialist toolset.

### Run 2 (81K tokens, 130s)

**Agent diagnosis:** P-CSCF `SCP_BIND_IP` placeholder in config + HTTP timeout too aggressive at 2s.

**Failure mode:** Both "causes" are pre-existing conditions visible in the baseline (`httpclient:connfail` was 1,386 before fault injection). The agent treated background noise as the root cause.

**Pipeline breakdown:**

| Phase | What happened | What should have happened |
|---|---|---|
| Triage | Did not flag UPF GTP counter deltas as significant | Should have recognized GTP anomalies + jitter buffer resets as data plane symptoms |
| EndToEndTracer | Consumed 43% of tokens on IMS call flow | Should have checked the data plane path (UPF) |
| Dispatch | Selected Transport + IMS, not Core | Should have selected Core — UPF is a core NF |
| TransportSpecialist | Focused on pre-existing P-CSCF HTTP failures | Toolset narrowing helped (14K vs 33K tokens) but still wrong target |
| IMSSpecialist | Correctly scoped but fault wasn't in IMS | Expected behavior — correct scope, wrong specialist dispatched |
| Synthesis | Coherent synthesis of incorrect findings | Garbage in, garbage out |

**Structural root cause:** Core specialist was never dispatched. The UPF's Prometheus metrics and `tc` rules would only be examined by the Core specialist. The dispatcher saw IMS metric deltas and jitter buffer resets and attributed them to the application layer, failing to reason that these are secondary effects of an upstream data plane fault.

**Recommended fixes:**
1. Make `core` a mandatory specialist (same as existing `transport` always-include rule, ~5K tokens)
2. Give TriageAgent a `check_tc_rules` tool to catch netem rules during initial health scan
3. Add data plane symptom patterns to dispatcher prompt (jitter buffer resets + GTP anomalies → core)

---

## Cross-Cutting Patterns

### Why agents fail

1. **Top-down investigation** — attracted to interesting application-layer errors, skip network/transport checks
2. **Pre-existing noise** — treat baseline conditions as fault symptoms (httpclient:connfail, Diameter I_Open)
3. **Hallucination under ambiguity** — when tools return empty or ambiguous results, agents fabricate evidence
4. **Missing diagnostic reflexes** — tools exist but agents don't know WHEN to use them
5. **Single-ended verification** — check one side of a transaction, assume the other is fine
6. **Confirmation bias** — find a plausible hypothesis, stop investigating alternatives
7. **Overconfidence** — express "high confidence" on completely wrong diagnoses

### Why agents succeed

1. **Metrics-first triage** — 3-second Prometheus query replaces 30-minute log spirals
2. **Clean failure signatures** — "hard down" faults (container killed/paused) with unambiguous metrics
3. **Methodology enforced in code, not prompts** — mandatory phases, tool restrictions, gated execution
4. **Checking both ends** of a transaction
5. **Parallel probes** — independent diagnostics run concurrently
6. **Clean context per specialist** — no 50K log dumps polluting reasoning

### What improved across versions

| Change | Impact |
|---|---|
| v1 → v1.5: Added `read_running_config` + `check_process_listeners` tools | 10% → 90% on call failure scenario |
| v3 → v4: Added network topology as first tool call | Triage correctly identifies RAN failures immediately |
| v4 Run 1 → Run 2: Removed `run_kamcmd` from TransportSpecialist | Eliminated SIP-layer hallucinations, tokens dropped 33K → 14K |
| Mandatory transport specialist inclusion | Ensures transport layer always checked |

### What still needs fixing

1. **Core specialist not dispatched for data plane faults** — UPF issues invisible without it
2. **Dispatcher doesn't map data plane symptoms to core specialist** — jitter buffer resets, GTP anomalies not recognized
3. **TriageAgent lacks `check_tc_rules`** — cannot detect injected latency/loss during initial scan
4. **Specialists ignore triage findings** — correct triage output doesn't guarantee correct specialist output
5. **No baseline comparison** — agents cannot distinguish pre-existing conditions from injected faults

---

## Source Documents

| Document | Location |
|---|---|
| RCA Methodology Reflections | `docs/RCAs/rca_reflections.md` |
| Agent Design Reflections | `docs/RCAs/agent_design_reflections.md` |
| UE1→UE2 Call Failure Postmortem | `docs/RCAs/postmortem_ue1_calls_ue2_failure.md` |
| gNB Kill Three Runs Analysis | `docs/RCAs/gnb_kill_three_runs_analysis.md` |
| v3 P-CSCF Latency Episode | `agentic_ops_v3/docs/agent_logs/run_20260325_204757_p_cscf_latency.md` |
| v3 HSS Unresponsive Episode | `agentic_ops_v3/docs/agent_logs/run_20260325_221035_hss_unresponsive.md` |
| v4 gNB Radio Link Failure | `agentic_ops_v4/docs/agent_logs/run_20260326_231102_gnb_radio_link_failure.md` |
| v4 Data Plane Degradation (Run 1) | `agentic_ops_v4/docs/agent_logs/run_20260327_161736_data_plane_degradation.json` |
| v4 Data Plane Degradation (Run 2) | `agentic_ops_v4/docs/agent_logs/run_20260327_163009_data_plane_degradation.json` |
