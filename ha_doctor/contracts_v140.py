"""Central public contracts for HA Doctor 0.14 Consolidated Decision Engine."""

VERSION = "0.14.0"
REPORT_SCHEMA = "ha-doctor-report/0.14"
SHARE_SCHEMA = "ha-doctor-share/8"
SHARE_MODEL = "assistant_share_report_v8"
SHARE_TARGET_BYTES = 26_000
SHARE_HARD_BYTES = 30_000

PRODUCT_MODEL = "doctor_view_v6_consolidated_decision"
TRIAGE_MODEL = "triage_board_v6_operational_lanes"
TRUST_MODEL = "diagnostic_trust_v6_native_self_check"
SELF_CHECK_MODEL = "report_self_check_v6_native_contracts"
READINESS_MODEL = "release_readiness_v6_native_gate"
QUALITY_MODEL = "quality_gates_v12_native_contracts"
TEMPORAL_MODEL = "temporal_v5_publication_aware_history"
HISTORY_CONTRACT = "published_primary_score_v1"
HISTORY_POLICY = "publication_complete_required_v1"
SCORE_TRACE_MODEL = "score_change_trace_v4_publication_aware"
CONDITION_MODEL = "condition_semantics_v9_branch_policy_overlap"
CONTROLLER_REVIEW_MODEL = "controller_review_summary_v5_policy_overlap"
ACTION_PLAN_MODEL = "correlated_action_plan_v6_operational_decision"
ACTION_PLAN_SOURCE = "final_operational_action_plan_v140"
DECISION_MODEL = "decision_engine_v2_operational_lanes"
ENTITY_ATTENTION_MODEL = "entity_attention_v3_root_cause_first"
REPAIR_PLAYBOOK_MODEL = "repair_playbook_v2_evidence_scoped"
POLICY_CONFLICT_MODEL = "branch_policy_overlap_v1"

VERDICT_CODES = {"healthy", "monitor", "needs_attention", "action_required", "critical"}
EVIDENCE_LEVELS = {"confirmed", "probable", "hypothesis"}
REPAIR_READINESS = {
    "ready_for_manual_change", "needs_logic_review", "external_dependency",
    "watch_external", "observe_only", "optimization",
}
OPERATIONAL_LANES = {"fix_now", "logic_review", "restore_if_needed", "watch", "optimize"}
