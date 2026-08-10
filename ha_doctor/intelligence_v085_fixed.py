"""Safety wiring for HA Doctor 0.8.5."""
import intelligence_v085 as base
import semantics_v085_fixed as semantics

VERSION = "0.8.5"
REPORT_SCHEMA_VERSION = base.REPORT_SCHEMA_VERSION
SCORE_MODEL = base.SCORE_MODEL

# The orchestrator resolves this symbol at runtime, so use the hardened proof
# implementation without duplicating the rest of the 0.8.5 pipeline.
base.build_condition_semantics_v5 = semantics.build_condition_semantics_v5
base.CONDITION_MODEL = semantics.CONDITION_MODEL


def enrich_v085(report, history_path="/data/ha-doctor-history.json"):
    return base.enrich_v085(report, history_path=history_path)
