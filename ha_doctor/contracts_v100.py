"""Central public contracts for HA Doctor 0.10 Engine Candidate."""

VERSION = "0.10.0"
REPORT_SCHEMA = "ha-doctor-report/0.10"
SHARE_SCHEMA = "ha-doctor-share/4"
SHARE_MODEL = "assistant_share_report_v4"
SHARE_TARGET_BYTES = 28_000
SHARE_HARD_BYTES = 32_000

PRODUCT_MODEL = "doctor_view_v2_engine_candidate"
TRIAGE_MODEL = "triage_board_v2_explainable"
TRUST_MODEL = "diagnostic_trust_v2_coverage_aware"
SELF_CHECK_MODEL = "report_self_check_v2_cross_contract"
READINESS_MODEL = "release_readiness_v2_engine_candidate"
QUALITY_MODEL = "quality_gates_v8_engine_candidate"
CONDITION_MODEL = "condition_semantics_v7_overlap_evidence"
RESILIENCE_MODEL = "resilience_spof_v4_role_aware"
RESILIENCE_RECOMMENDATION_MODEL = "resilience_recommendations_v3_exposure_first"

VERDICT_CODES = {"healthy", "monitor", "needs_attention", "action_required", "critical"}
EVIDENCE_LEVELS = {"confirmed", "probable", "hypothesis"}
