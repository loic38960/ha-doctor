"""Central public contracts for HA Doctor 0.16 Evidence Precision Engine."""

VERSION = "0.16.1"
REPORT_SCHEMA = "ha-doctor-report/0.16"
SHARE_SCHEMA = "ha-doctor-share/10"
SHARE_MODEL = "assistant_share_report_v10"
SHARE_TARGET_BYTES = 20_000
SHARE_HARD_BYTES = 24_000

PRODUCT_MODEL = "doctor_view_v8_evidence_precision"
TRIAGE_MODEL = "triage_board_v8_precision_order"
TRUST_MODEL = "diagnostic_trust_v8_precision_validated"
SELF_CHECK_MODEL = "report_self_check_v8_precision_truth"
READINESS_MODEL = "release_readiness_v8_precision_gate"
QUALITY_MODEL = "quality_gates_v14_precision_validated"
TEMPORAL_MODEL = "temporal_v7_published_baseline_visibility"
HISTORY_CONTRACT = "published_primary_score_v1"
HISTORY_POLICY = "publication_complete_required_v1"
PUBLICATION_MODEL = "publication_transaction_v1"
SCORE_TRACE_MODEL = "score_change_trace_v6_published_baseline"

CONDITION_MODEL = "condition_semantics_v11_evidence_precision"
CONTROLLER_REVIEW_MODEL = "controller_review_summary_v7_exact_scope"
CONTROLLER_IMPACT_MODEL = "controller_impact_v2_unresolved_scope"
RESILIENCE_MODEL = "resilience_precision_v5_phase_aware"
RESILIENCE_RECOMMENDATION_MODEL = "resilience_recommendations_v4_phase_aware"
LOOP_MODEL = "automation_feedback_v1_intent_aware"
DUPLICATE_MODEL = "duplicate_action_semantics_v1"

ACTION_PLAN_MODEL = "correlated_action_plan_v8_precision_order"
ACTION_PLAN_SOURCE = "final_precision_action_plan_v160"
DECISION_MODEL = "decision_engine_v4_precision_board"
CANONICAL_ORDER_MODEL = "canonical_decision_order_v1"
ENTITY_ATTENTION_MODEL = "entity_attention_v5_precision_scope"
REPAIR_PLAYBOOK_MODEL = "repair_playbook_v4_precision_evidence"
PUBLIC_TRUTH_MODEL = "public_contract_truth_v5_precision"

VERDICT_CODES = {"healthy", "monitor", "needs_attention", "action_required", "critical"}
EVIDENCE_LEVELS = {"confirmed", "probable", "hypothesis"}
OPERATIONAL_LANES = {"fix_now", "logic_review", "restore_if_needed", "watch", "optimize"}
REPAIR_READINESS = {
    "ready_for_manual_change", "needs_logic_review", "external_dependency",
    "watch_external", "observe_only", "optimization",
}
