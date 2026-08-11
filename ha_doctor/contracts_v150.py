"""Central public contracts for HA Doctor 0.15 Trust & Publication Engine."""

VERSION = "0.15.0"
REPORT_SCHEMA = "ha-doctor-report/0.15"
SHARE_SCHEMA = "ha-doctor-share/9"
SHARE_MODEL = "assistant_share_report_v9"
SHARE_TARGET_BYTES = 22_000
SHARE_HARD_BYTES = 26_000

PRODUCT_MODEL = "doctor_view_v7_trust_first"
TRIAGE_MODEL = "triage_board_v7_operational_summary"
TRUST_MODEL = "diagnostic_trust_v7_publication_safe"
SELF_CHECK_MODEL = "report_self_check_v7_final_export_truth"
READINESS_MODEL = "release_readiness_v7_publication_transaction"
QUALITY_MODEL = "quality_gates_v13_publication_safe"
TEMPORAL_MODEL = "temporal_v6_publication_transaction"
HISTORY_CONTRACT = "published_primary_score_v1"
HISTORY_POLICY = "publication_complete_required_v1"
PUBLICATION_MODEL = "publication_transaction_v1"
SCORE_TRACE_MODEL = "score_change_trace_v5_publication_transaction"
CONDITION_MODEL = "condition_semantics_v10_event_window_policy"
CONTROLLER_REVIEW_MODEL = "controller_review_summary_v6_event_window"
ACTION_PLAN_MODEL = "correlated_action_plan_v7_operational_summary"
ACTION_PLAN_SOURCE = "final_operational_action_plan_v150"
DECISION_MODEL = "decision_engine_v3_execution_board"
ENTITY_ATTENTION_MODEL = "entity_attention_v4_operational_summary"
REPAIR_PLAYBOOK_MODEL = "repair_playbook_v3_event_aware"
POLICY_CONFLICT_MODEL = "event_window_policy_overlap_v2"
PUBLIC_TRUTH_MODEL = "public_contract_truth_v4_pre_selfcheck"

VERDICT_CODES = {"healthy", "monitor", "needs_attention", "action_required", "critical"}
EVIDENCE_LEVELS = {"confirmed", "probable", "hypothesis"}
REPAIR_READINESS = {
    "ready_for_manual_change", "needs_logic_review", "external_dependency",
    "watch_external", "observe_only", "optimization",
}
OPERATIONAL_LANES = {"fix_now", "logic_review", "restore_if_needed", "watch", "optimize"}
