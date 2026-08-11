"""Public contracts for HA Doctor 0.17 Resolution & Attribution Engine."""

VERSION = "0.17.0"
REPORT_SCHEMA = "ha-doctor-report/0.17"
SHARE_SCHEMA = "ha-doctor-share/11"
SHARE_MODEL = "assistant_share_report_v11"
SHARE_TARGET_BYTES = 18_000
SHARE_HARD_BYTES = 22_000

PRODUCT_MODEL = "doctor_view_v9_resolution_attribution"
TRUST_MODEL = "diagnostic_trust_v9_resolution_attribution"
SELF_CHECK_MODEL = "report_self_check_v9_resolution_truth"
QUALITY_MODEL = "quality_gates_v15_resolution_attribution"
TEMPORAL_MODEL = "temporal_v8_domain_attribution"
SCORE_ATTRIBUTION_MODEL = "score_attribution_v1_domain_delta"
HISTORY_CONTRACT = "published_primary_score_v1"
HISTORY_POLICY = "publication_complete_required_v1"
PUBLICATION_MODEL = "publication_transaction_v1"

CONDITION_MODEL = "condition_semantics_v11_evidence_precision"
CONTROLLER_REVIEW_MODEL = "controller_review_summary_v8_resolution_context"
CONTROLLER_IMPACT_MODEL = "controller_impact_v2_unresolved_scope"
RESILIENCE_MODEL = "resilience_precision_v6_guard_actionable"
RESILIENCE_RECOMMENDATION_MODEL = "resilience_recommendations_v5_guard_actionable"
FEEDBACK_MODEL = "automation_feedback_v2_transition_proof"
DUPLICATE_MODEL = "duplicate_action_semantics_v2_resolution_ready"
REFERENCE_MODEL = "missing_reference_intelligence_v1"
RESOLUTION_MODEL = "diagnostic_resolution_v1"

ACTION_PLAN_MODEL = "correlated_action_plan_v9_resolution_order"
ACTION_PLAN_SOURCE = "final_resolution_action_plan_v170"
DECISION_MODEL = "decision_engine_v5_resolution_board"
CANONICAL_ORDER_MODEL = "canonical_decision_order_v2_resolution"
REPAIR_PLAYBOOK_MODEL = "repair_playbook_v5_resolution_evidence"
PUBLIC_TRUTH_MODEL = "public_contract_truth_v6_resolution"

OPERATIONAL_LANES = {"fix_now", "logic_review", "restore_if_needed", "watch", "optimize"}
REPAIR_READINESS = {
    "ready_for_manual_change", "needs_logic_review", "external_dependency",
    "watch_external", "observe_only", "optimization", "resolved_static",
}
RESOLUTION_STATUSES = {
    "manual_fix_ready", "logic_review_required", "watch_only", "optimization",
    "statically_resolved", "external_restore_if_needed",
}
