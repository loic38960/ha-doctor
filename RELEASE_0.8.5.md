# HA Doctor 0.8.5 — Branch Intelligence

0.8.5 is a focused hardening release built from the first real 0.8.4 field report.

## What changed

- **Condition Semantics V5** follows deterministic action branches instead of comparing only whole-automation intent.
- **Helper phase protocols** can prove handoffs such as `priority=on -> actuator off -> priority=off -> actuator resume` without executing Jinja.
- A controller pair is de-escalated only when **all opposing deterministic command paths** have explicit phase evidence.
- Guards on the target actuator itself are explicitly excluded as proof of mutual exclusion.
- **Consistency V5** cross-checks the single state snapshot, entity-health totals, architecture counters, executive summary, controller-pair counts and Score V5 projections.
- **Score V5 Preview V2** adds a small usage factor for registry incidents that affect no automation, while keeping real offline hardware penalized and leaving the historical Score V4 untouched.
- Version-specific stale plan wording has been removed from the generated report.

## Safety model

0.8.5 remains local and read-only. It does not execute templates, modify Home Assistant configuration, persist raw state values, read `secrets.yaml`, or apply automatic repairs.

## Validation target

The next real scan should confirm whether the previously unresolved pool-controller pairs are reduced without hiding the genuinely ambiguous water-heater/rotation cases. The primary V4 score is intentionally unchanged by this release.
