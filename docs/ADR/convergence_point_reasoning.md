# ADR: Convergence Point Reasoning — Grounding the Network Analyst in 3GPP Traffic Path Architecture

**Date:** 2026-04-13
**Status:** Accepted
**Related episodes:**
- [`docs/critical-observations/run_20260409_231143_data_plane_degradation.md`](../critical-observations/run_20260409_231143_data_plane_degradation.md) — first data plane degradation run (0% score, agent diagnosed IMS signaling storm, UPF never mentioned)
- [`docs/critical-observations/run_20260413_024554_data_plane_degradation.md`](../critical-observations/run_20260413_024554_data_plane_degradation.md) — second run (0% score, SMF crashed due to PFCP disruption from UPF loss, agent correctly found crash but missed injected fault)
- [`agentic_ops_v5/docs/agent_logs/run_20260413_032529_data_plane_degradation.md`](../../agentic_ops_v5/docs/agent_logs/run_20260413_032529_data_plane_degradation.md) — third run (50% score, agent said "packet loss happening in UPF" but attributed cause to P-CSCF→PCF Rx failure and listed root cause as "Unknown")
- [`docs/critical-observations/run_20260408_144319_hss_unresponsive.md`](../critical-observations/run_20260408_144319_hss_unresponsive.md) — HSS episode where the agent misattributed an IMS component to the infrastructure layer (prompted the `layer_accuracy` scorer dimension)

---

## Decision

Three coordinated changes to ground the Network Analyst's causal reasoning in the actual 3GPP network architecture, preventing fabricated causal chains and enabling diagnosis of faults at convergence points like the UPF.

### 1. Traffic Path Separation rules in the Network Analyst prompt

Added a mandatory reasoning section to `agentic_ops_v5/prompts/network_analyst.md` that encodes the fundamental 3GPP architectural principle: NF-to-NF control plane traffic is direct between containers, while UE-originated traffic traverses GTP-U tunnels through the UPF. The agent must validate every causal hypothesis against the topology before asserting it.

### 2. Convergence Point Analysis in the Network Analyst prompt

Added a mandatory diagnostic pattern: when anomalies appear simultaneously in IMS signaling AND data plane quality (RTPEngine), the agent must check the UPF as the shared upstream dependency before attributing the symptoms to the IMS layer. The UPF is explicitly identified as the convergence point where UE signaling and media paths merge.

### 3. Enhanced UPF causal chain with convergence point data in the ontology

Updated `network_ontology/data/causal_chains.yaml` to encode which traffic paths traverse the UPF and which do not, plus a derived anomaly detection feature that detects UPF degradation during active calls.

---

## Context

### The problem: fabricated causal chains

Across three consecutive runs of the Data Plane Degradation scenario (30% packet loss on UPF), the Ops agent consistently fabricated causal chains that didn't match the actual network architecture:

**Run 1 (0% score):** The agent diagnosed an IMS signaling storm caused by a stuck Diameter connection at the I-CSCF. The UPF was never mentioned. The anomaly screener flagged only IMS metrics (SIP rates 1000x+ above baseline) and no UPF metrics, because the trained model saw near-zero UPF rates as normal.

**Run 2 (0% score):** The SMF crashed 9 seconds after fault injection due to an Open5GS assertion failure (`ogs_nas_build_qos_flow_descriptions`) caused by PFCP disruption from UPF packet loss. The agent correctly diagnosed the SMF crash — a real failure — but it wasn't the injected fault.

**Run 3 (50% score):** The agent made progress — it stated "the packet loss is happening in the user plane (UPF)" and noted 45% RTPEngine loss. But it hypothesized that P-CSCF → PCF (Rx) connection failures caused the UPF packet loss. This causal chain is architecturally impossible: the Rx interface between P-CSCF and PCF is a direct connection on the container network; it does not traverse the UPF.

The agent had access to `get_network_topology` which clearly shows P-CSCF connects directly to PCF (Rx edge) with no UPF in between. But the prompt never told the agent to validate its causal hypotheses against the topology. The agent treated the topology as a component inventory, not as a constraint on what can cause what.

### Why the LLM fabricates causal chains

The LLM has general telecom knowledge and can reason about 5G architecture. But under the pressure of the pipeline — anomaly screener flags demanding attention, 10 mandatory tool calls to process, layer ratings to produce — it takes the path of least resistance: see correlated metrics, assert causation. It doesn't pause to ask "does this causal chain match the actual network topology?"

The anomaly screener exacerbates this. Its top flags are always IMS signaling metrics (1000x+ deviation from baseline), which anchor the agent's attention on the IMS layer. UPF metrics either don't appear (run 1) or appear as minor signals overshadowed by IMS noise (run 3). The agent follows the loudest signal.

### The 3GPP architectural principle the agent was missing

**TS 23.501 (5G System Architecture)** defines the separation of user plane and control plane (CUPS — Control and User Plane Separation) as a core architectural principle. In this stack:

**User plane (through UPF):**
- UE SIP signaling: UE → gNB → UPF → P-CSCF (SIP REGISTER, INVITE inside GTP-U)
- RTP media: UE → gNB → UPF → RTPEngine
- Internet data: UE → gNB → UPF → data network

**Control plane (direct between NFs, NOT through UPF):**
- SBI (HTTP/2): AMF ↔ SMF ↔ PCF ↔ UDM — direct on container network
- Diameter Cx: I-CSCF/S-CSCF ↔ HSS — direct
- Diameter Rx: P-CSCF ↔ PCF — direct
- SIP Mw: P-CSCF ↔ I-CSCF ↔ S-CSCF — direct
- PFCP N4: SMF ↔ UPF — direct (control plane, not through GTP-U)

**Consequence:** A fault on the UPF affects UE-originated traffic but does NOT affect NF-to-NF communication. The agent's hypothesis in run 3 — that P-CSCF → PCF Rx failures caused UPF packet loss — is architecturally impossible because Rx traffic doesn't touch the UPF.

**The convergence point pattern:** The UPF is where UE signaling and UE media paths converge. When BOTH IMS signaling (SIP retransmissions from UEs) AND media quality (RTPEngine packet loss) degrade simultaneously, the shared upstream dependency is the UPF. This is the diagnostic fingerprint of a user plane fault — not an IMS-layer problem.

---

## Design

### Network Analyst prompt changes

Two new mandatory sections added between Step 3 (layer rating) and Step 4 (suspect identification):

**Traffic Path Separation** — Lists which traffic paths go through the UPF and which don't. Instructs the agent: *"Before hypothesizing that a fault on component X caused symptoms at component Y, verify from `get_network_topology` that Y's traffic path actually traverses X."* Provides concrete examples of what UPF faults can and cannot cause.

**Convergence Point Analysis** — Defines the diagnostic pattern: when IMS signaling AND RTPEngine quality both degrade, the agent MUST call `get_causal_chain_for_component("upf")`, check UPF data plane gauges, run `measure_rtt` from gNB to UPF, and rate UPF as the primary suspect. Explicitly forbids attributing the combined pattern to an IMS-layer cause.

These sections activate the LLM's existing 3GPP knowledge by providing a structured reasoning framework. The model already knows about CUPS and GTP-U encapsulation — it just needs the prompt to tell it "use that knowledge to validate your hypotheses."

### Causal chain ontology changes

The UPF N3 degradation causal chain in `causal_chains.yaml` gained three enhancements:

**`convergence_point` section** — Documents which paths traverse the UPF and which don't, stored as structured data that the `get_causal_chain_for_component` tool returns. When the agent calls this tool for the UPF, it gets explicit guidance: *"If RTPEngine shows packet loss AND IMS CSCFs show elevated SIP rates/timeouts simultaneously, the UPF is the common upstream cause."*

**Updated cascading effects** — The old chain said *"May timeout if SIP signaling traverses the degraded data plane"* (vague). The new chain says *"SIP messages from UEs are dropped/delayed, causing retransmissions that appear as an IMS signaling storm at all CSCFs"* (specific, explains the symptom the agent actually observes).

**Expanded `does_NOT_mean`** — Added explicit false causal chains: *"P-CSCF → PCF (Rx) failure — the Rx interface is direct between P-CSCF and PCF, not through the UPF"* and *"Diameter peer issue at I-CSCF or S-CSCF — Cx interface is direct to HSS, not through UPF"*. These directly counter the incorrect hypotheses the agent produced in runs 1 and 3.

### Derived anomaly feature: `upf_activity_during_calls`

Added to `agentic_ops_v5/anomaly/preprocessor.py`. This addresses the fundamental problem that the anomaly model couldn't distinguish "UPF idle between traffic bursts" (normal) from "UPF degraded during active calls" (fault).

The feature computes: `actual_upf_rate / expected_upf_rate` conditioned on active calls (`dialog_ng:active > 0`).

| State | Active calls? | UPF rate | Feature value | Model sees |
|---|---|---|---|---|
| Healthy idle | No | ~0 | 1.0 | Normal |
| Healthy call | Yes | ~100 pps | ~1.0 | Normal |
| Fault during call | Yes | ~0 | ~0.0 | **Anomalous** |
| Fault while idle | No | ~0 | 1.0 | Normal (undetectable) |

During training (healthy stack with traffic), this feature is always near 1.0. During a UPF fault with active calls, it drops to ~0.0. The old raw UPF rate feature had min=0.0 in training (from idle periods), so zero during a fault was indistinguishable from idle. The conditional feature eliminates this ambiguity.

The feature uses `dialog_ng:active` from P-CSCF or S-CSCF as the call activity indicator, and assumes ~100 pps per active G.711 call (50 pps per direction at 20ms packetization) as the expected rate. The normalization caps at 1.0 so the feature stays in [0, 1].

---

## Files Changed

**Modified:**
- `agentic_ops_v5/prompts/network_analyst.md` — Two new mandatory sections: Traffic Path Separation and Convergence Point Analysis
- `network_ontology/data/causal_chains.yaml` — Enhanced UPF N3 degradation chain with `convergence_point` data, updated cascading effects, expanded `does_NOT_mean`
- `agentic_ops_v5/anomaly/preprocessor.py` — Added `derived.upf_activity_during_calls` computed feature

---

## What This Doesn't Solve

1. **The Investigator execution failure.** In run 3, the InvestigatorAgent produced zero output despite making 6 tool calls. This is an ADK/Gemini execution issue, not a reasoning issue. The Network Analyst's improved guidance only helps if the downstream agents actually execute.

2. **The scenario design problem.** tc netem on UPF's eth0 affects ALL traffic (GTP-U, PFCP, N6), not just the data plane. This can cause cascading control plane failures (like the SMF crash in run 2). The prompt changes help the agent reason correctly about the UPF as root cause, but the scenario may still produce unexpected cascading failures.

3. **UPF metrics don't self-report drops.** Open5GS UPF counts packets it hands to the kernel, not packets that actually reach the destination. tc netem drops happen after the UPF's counters increment. The agent still cannot directly observe "30% packet loss on UPF" from UPF's own metrics — it must infer it from downstream effects (RTPEngine loss, SIP retransmissions, elevated RTT on `measure_rtt`).

---

## Verification

After retraining the anomaly model (`python -m anomaly_trainer --duration 300`), run the Data Plane Degradation scenario and check:

1. **Anomaly screener** should flag `derived.upf_activity_during_calls` dropping below 1.0 (if calls were active during the fault)
2. **Network Analyst** should cite the convergence point pattern: simultaneous IMS signaling + RTPEngine degradation → UPF as primary suspect
3. **Network Analyst** should NOT hypothesize that P-CSCF → PCF (Rx) failures caused UPF issues
4. **UPF** should appear in `suspect_components` as primary/high confidence
5. **Core layer** should be rated YELLOW or RED for the UPF, not GREEN
