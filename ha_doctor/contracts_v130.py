"""Central public contracts for HA Doctor 0.13 Decision Engine."""

VERSION = "0.13.0"
REPORT_SCHEMA = "ha-doctor-report/0.13"
SHARE_SCHEMA = "ha-doctor-share/7"
SHARE_MODEL = "assistant_share_report_v7"
SHARE_TARGET_BYTES = 28_000
SHARE_HARD_BYTES = 32_000

PRODUCT_MODEL = "doctor_view_v5_decision_engine"
TRIAGE_MODEL = "triage_board_v5_operational_relevance"
TRUST_MODEL = "diagnostic_trust_v5_decision_evidence"
SELF_CHECK_MODEL = "report_self_check_v5_decision_contracts"
READINESS_MODEL = "release_readiness_v5_decision_engine"
QUALITY_MODEL = "quality_gates_v11_decision_engine"
TEMPORAL_MODEL = "temporal_v4_canonical_published_score"
HISTORY_CONTRACT = "published_primary_score_v1"
SCORE_TRACE_MODEL = "score_change_trace_v3_canonical_history"
CONDITION_MODEL = "condition_semantics_v8_mandatory_guard_matrix"
CONTROLLER_REVIEW_MODEL = "controller_review_summary_v4_guard_matrix"
ACTION_PLAN_MODEL = "correlated_action_plan_v5_decision_engine"
ACTION_PLAN_SOURCE = "final_decision_action_plan_v130"
DECISION_MODEL = "decision_engine_v1_evidence_playbooks"
ENTITY_ATTENTION_MODEL = "entity_attention_v2_operational_relevance"
REPAIR_PLAYBOOK_MODEL = "repair_playbook_v1_read_only"

VERDICT_CODES = {"healthy", "monitor", "needs_attention", "action_required", "critical"}
EVIDENCE_LEVELS = {"confirmed", "probable", "hypothesis"}
REPAIR_READINESS = {"ready_for_manual_change", "needs_logic_review", "external_dependency", "observe_only", "optimization"}
