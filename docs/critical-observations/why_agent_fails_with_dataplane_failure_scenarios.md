## Agent consistently fails diagnosing data plane quality degradation failure
Several attempts at designing and tweaking agent's diagnostic capabilities have all failed to enable it to correctly identify the root cause when it comes to data plane quality degradation failure scenario.

While the underlying improvements in the anomaly model, metrics and diagnostics tools have enabled the Network Analyst agent to correctly identify RTPEngine as the top or one of the top suspects, and IG has mostly (with few exceptions) managed to genearte the right hypothese and falsification plans, Investigator agents have consistently failed to correctly prove or disprove hypotheses.

Let's look at three runs and analyze the agent'e behavior.

## Clean and correct hypothesis disproven by investigator

In run_20260502_172113_call_quality_degradation.md, there is one (and only one!) hypothesis correctly pointing to RTPEngine:

**Hypothesis:** RTPEngine is the source of extensive packet loss on the media plane. While the UPF is processing a high volume of user plane traffic, RTPEngine's own metrics report a severe packet loss ratio, indicating it is failing to relay RTP packets correctly.

Three probes are proposed to investigate the hypothesis:
- **`get_dp_quality_gauges`** — Returns rate-based MOS/loss/jitter alongside RTPEngine errors.
- **`get_dp_quality_gauges`** — window_seconds=120 to confirm MOS drop and packet-loss percentage across the same window
- **`get_dp_quality_gauges`** — Check UPF in/out symmetry in the output.

Investigator agent runs these probes and disproves them! It then give it a second shot and disproves them again! Why?
- **Returns rate-based MOS/loss/jitter alongside RTPEngine errors.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_diagnostic_metrics(at_time_ts = 1777742116.7580352, nfs = ["rtpengine"]))`
    - *Observation:* [EVIDENCE: get_diagnostic_metrics(at_time_ts=1777742116.7580352, nfs=["rtpengine"]) -> "rtpengine.errors_per_second_(total) = 0"]
    - *Comment:* The hypothesis expected a non-zero error count from RTPEngine, but the metric is zero. This falsifies the expectation that RTPEngine is aware of and reporting errors.

- **window_seconds=120 to confirm MOS drop and packet-loss percentage across the same window** ✓ CONSISTENT
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1777742116.7580352, window_seconds = 120))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777742116.7580352, window_seconds=120) -> "RTPEngine:\n    loss (recent)  : 25.05"]
    - *Comment:* The observed high packet loss ratio is consistent with the hypothesis and the initial NA report. However, this metric reflects the end-to-end quality and does not by itself isolate the source of the loss.
--> even though it sees the high error rate in RTPEngine, LLM simply dimisses it as end-to-end issue and not isolated to RTPEngine. This fabrication is very interesting. It most definitely has to do with the fact that the first probe disproved RTPEngine issue ("rtpengine.errors_per_second_(total) = 0") and LLM invents reasons to continue solidifying the same narrative.

- **Check UPF in/out symmetry in the output.** ✗ CONTRADICTS
    - *Tool:* `print(default_api.get_dp_quality_gauges(at_time_ts = 1777742116.7580352, window_seconds = 120))`
    - *Observation:* [EVIDENCE: get_dp_quality_gauges(at_time_ts=1777742116.7580352, window_seconds=120) -> "UPF:\n    in  packets/sec: 8.9\n    out packets/sec: 6.8"]
    - *Comment:* The UPF's inbound packet rate is significantly higher than its outbound rate. This asymmetry indicates that packets are being dropped within the UPF, which contradicts the hypothesis that RTPEngine is the source of the loss.

--> And this third issue (incorrectly assuming that UPF rate/number of uplink and downlink packets must be almost symmetrical), completely taints investigator's judgement and not only misleads it to completely disprove RTPEngine as the culprint, it then proceeds to suggest UPF as the alternative source of failure.    

Similar underlying reasons are seen in other episodes such as in run_20260504_151835_call_quality_degradation.md where the agent basically relies on asymmetrical rate of uplink and downlink packets in UPF to identify UPF as the root cause of data plane quality degradation. 

In run_20260504_160632_call_quality_degradation.md episode, RTPEngine failure hypothesis was disproven because of two main reasons:
    1) Shot 1: The hypothesis that RTPEngine's media processing is the source of failure is contradicted by the evidence. A specific probe for internal RTPEngine errors showed a rate of zero.
    2) Shot 2: The investigation is inconclusive. One probe confirmed high packet loss related to RTPEngine and the UPF, which is consistent with the hypothesis. However, the two subsequent probes designed to isolate the fault to either RTPEngine's network path or the UPF itself could not be executed due to technical limitations (missing 'ping' in one container, incorrect container name in the plan for the other)

The recent improvements in terms of agent orchstration and all the guardrails have been quite successful. The overal agentic workflow, multi-shot reasoning, and confidence levels underpinning the diagnostics have all considerably improved. However, there are a few fundamental issues causing the investigator agents to trip over and misdiagnose the failures:

## Absence of RTPEngine internal error
Every time the investigator agent runs probes to measure RTPEngine internal error rate, it finds it to be zero, which contradicts the hypotheis. So it proceeds to disprove it.

## UPF uplink and downlink assymetry misinterpretation
Agent (correctly) decides to runs this probe in the context of data plane issues and interprets the asymmetry between uplink and downlink traffic rate as packets being lost inside UPF. So it consistenyl proposes UPF to be the root cause of data plane issues and attributes RTPEngine high error rate to UPF failure and a downstream effect of that.

## Tooling issues in RTPEngine
RTPEngine container does not have ping so running measure_rtt fails. This probe could have definitively guided the agent to the root cause, but it doesn't run and agent marks the evidence as inconclusive.

## Way forward
Addressing these 3 issues should cause a meaningful boost in agent's behavior.
1) RTPEngine internal error rate - look into why the internal error rate is perceived as 0. What tool and metrics does the investigator agent use for this claim? If there is a metric that is indeed zero, do we need to create a new metric?
2) UPF symmetrical uplink and downlink myth - Why does the investigator agent constanty fall into this trap? Should uplink and downlink be symmertical? If not, how can we burn this knowledge into the agent's working knowledge base?
3) add ping to RTPEngine container (and any other container that does not have it) to enable agents to measure RTT when needed. 

## get_flows_through_component probe
The probe "get_flows_through_component" appears in several falsification plans. How is it actually used by Investigator agent? It's quite good if used to understand what the flow looks like with the goal of checking relevant metrics os containers along the way. But if it is used to generically reasons about containers communicating with one another during a particular flow, as opposed to this particular deployment and failure scenario, then it needs to be refined.

## References to ADR decisions leaking in Agent's reasoning
Reading recent episodes, traces to ADR decisions such as A1+A2 linting and guardails are seen! Check how and why the agent is leaking such details. Most likely it sees them somewhere in the knowledge base or in its prompt.