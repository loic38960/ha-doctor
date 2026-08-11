"""Central public contracts for HA Doctor 0.12 Temporal Truth Engine."""

VERSION = "0.12.0"
REPORT_SCHEMA = "ha-doctor-report/0.12"
SHARE_SCHEMA = "ha-doctor-share/6"
SHARE_MODEL = "assistant_share_report_v6"
SHARE_TARGET_BYTES = 28_000
SHARE_HARD_BYTES = 32_000

PRODUCT_MODEL = "doctor_view_v4_temporal_truth"
TRIAGE_MODEL = "triage_board_v4_temporal_truth"
TRUST_MODEL = "diagnostic_trust_v4_temporal_truth"
SELF_CHECK_MODEL = "report_self_check_v4_temporal_contracts"
READINESS_MODEL = "release_readiness_v4_temporal_truth"
QUALITY_MODEL = "quality_gates_v10_temporal_truth"
TEMPORAL_MODEL = "temporal_v4_canonical_published_score"
HISTORY_CONTRACT = "published_primary_score_v1"
SCORE_TRACE_MODEL = "score_change_trace_v3_canonical_history"
CONTROLLER_REVIEW_MODEL = "controller_review_summary_v3_evidence"
ACTION_PLAN_MODEL = "correlated_action_plan_v4_temporal_truth"
ACTION_PLAN_SOURCE = "final_cross_validated_action_plan_v120"

VERDICT_CODES = {"healthy", "monitor", "needs_attention", "action_required", "critical"}
EVIDENCE_LEVELS = {"confirmed", "probable", "hypothesis"}
