"""Central public contracts for HA Doctor 0.11 Cross-Validated Engine."""

VERSION = "0.11.0"
REPORT_SCHEMA = "ha-doctor-report/0.11"
SHARE_SCHEMA = "ha-doctor-share/5"
SHARE_MODEL = "assistant_share_report_v5"
SHARE_TARGET_BYTES = 28_000
SHARE_HARD_BYTES = 32_000

PRODUCT_MODEL = "doctor_view_v3_cross_validated"
TRIAGE_MODEL = "triage_board_v3_traceable"
TRUST_MODEL = "diagnostic_trust_v3_cross_validated"
SELF_CHECK_MODEL = "report_self_check_v3_export_validated"
READINESS_MODEL = "release_readiness_v3_cross_validated"
QUALITY_MODEL = "quality_gates_v9_cross_validated"
CONDITION_MODEL = "condition_semantics_v7_overlap_evidence"
RESILIENCE_MODEL = "resilience_spof_v4_role_aware"
RESILIENCE_RECOMMENDATION_MODEL = "resilience_recommendations_v3_exposure_first"

VERDICT_CODES = {"healthy", "monitor", "needs_attention", "action_required", "critical"}
EVIDENCE_LEVELS = {"confirmed", "probable", "hypothesis"}
