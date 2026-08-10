"""HA Doctor 0.8.8 role-aware resilience analysis.

V4 keeps the V3 distinction between local helpers and external dependencies, then
adds operational role and explicit fail-safe handling:
- numeric_state triggers are fail-closed when the dependency is not read later;
- validity variables can gate every physical control branch;
- explicit valid/invalid branches count as deterministic handling;
- observational/helper-only consumers no longer inflate physical SPOF risk.

No template is executed and no Home Assistant state is persisted.
"""
from collections import Counter
import re

import intelligence_v080 as architecture_base
import resilience_v083 as base
from semantics_v081 import effective_automation_map, flow

VERSION = "0.8.8"
MODEL = "resilience_spof_v4_role_aware"
RECOMMENDATION_MODEL = "resilience_recommendations_v2_role_aware"
RULE_ID = "HD-RES-001"
DIAGNOSTIC_ID = "DX-HD-RES-001"

_INVALID_MARKERS = ("unknown", "unavailable")
_ENTITY_LITERAL_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$", re.IGNORECASE)
_STATES_LITERAL_RE = re.compile(
    r"""states\(\s*['\"](?P<entity>[a-z0-9_]+\.[a-z0-9_]+)['\"]\s*\)""",
    re.IGNORECASE,
)
_STATES_VAR_RE = re.compile(r"""states\(\s*(?P<var>[a-zA-Z_][a-zA-Z0-9_]*)\s*\)""")
_PHYSICAL_CONTROL_DOMAINS = {
    "alarm_control_panel", "button", "climate", "cover", "fan", "lawn_mower",
    "light", "lock", "media_player", "number", "remote", "select", "siren",
    "switch", "vacuum", "valve", "water_heater",
}


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _domain(entity_id):
    value = str(entity_id or "")
    return value.split(".", 1)[0] if "." in value else ""


def control_role(node):
    controls = [str(x) for x in (node.get("controls") or []) if x]
    if any(_domain(entity) in _PHYSICAL_CONTROL_DOMAINS for entity in controls):
        return "physical_control"
    if any(architecture_base._kind(entity) == "helper" for entity in controls):
        return "helper_control"
    if controls:
        return "other_control"
    return "observational"


def _variables(effective):
    value = effective.get("variables") if isinstance(effective, dict) else {}
    return value if isinstance(value, dict) else {}


def _entity_aliases(effective, entity_id):
    aliases = set()
    for name, value in _variables(effective).items():
        if isinstance(value, str) and _ENTITY_LITERAL_RE.fullmatch(value.strip()):
            if value.strip() == entity_id:
                aliases.add(str(name))
    return aliases


def _source_value_variables(effective, entity_id):
    variables = _variables(effective)
    aliases = _entity_aliases(effective, entity_id)
    sources = set(aliases)
    for name, value in variables.items():
        if not isinstance(value, str):
            continue
        if any(match.group("entity") == entity_id for match in _STATES_LITERAL_RE.finditer(value)):
            sources.add(str(name))
            continue
        for match in _STATES_VAR_RE.finditer(value):
            if match.group("var") in aliases:
                sources.add(str(name))
                break
    return sources


def validity_variables(effective, entity_id):
    variables = _variables(effective)
    sources = _source_value_variables(effective, entity_id)
    candidates = set()
    for name, value in variables.items():
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if not all(marker in lowered for marker in _INVALID_MARKERS):
            continue
        if "not in" not in lowered and "has_value" not in lowered:
            continue

        direct = any(match.group("entity") == entity_id for match in _STATES_LITERAL_RE.finditer(value))
        alias_read = any(match.group("var") in sources for match in _STATES_VAR_RE.finditer(value))
        source_var = any(re.search(rf"\b{re.escape(source)}\b", value) for source in sources)
        if direct or alias_read or source_var:
            candidates.add(str(name))
    return candidates


def _condition_strings(value):
    result = []
    if isinstance(value, str):
        result.append(value)
    elif isinstance(value, list):
        for item in value:
            result.extend(_condition_strings(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {"value_template", "conditions", "condition", "if"}:
                result.extend(_condition_strings(item))
    return result


def _validity_polarity(value, validity_vars):
    positive = negative = False
    for text in _condition_strings(value):
        lowered = text.lower()
        for name in validity_vars:
            token = str(name).lower()
            if not re.search(rf"\b{re.escape(token)}\b", lowered):
                continue
            if re.search(rf"\bnot\s+{re.escape(token)}\b", lowered) or re.search(
                rf"\b{re.escape(token)}\b\s*==\s*(?:false|0)", lowered
            ):
                negative = True
            else:
                positive = True
    return positive, negative


def _service(action):
    if not isinstance(action, dict):
        return ""
    service = action.get("service")
    if isinstance(service, str):
        return service
    raw = action.get("action")
    return raw if isinstance(raw, str) and "." in raw else ""


def _is_physical_service(action):
    service = _service(action)
    domain = service.split(".", 1)[0] if "." in service else ""
    return domain in _PHYSICAL_CONTROL_DOMAINS


def _physical_branch_validity(effective, validity_vars):
    if not validity_vars:
        return {"physical_commands": 0, "positive_gated": 0, "negative_handled": 0, "ungated": 0}

    stats = Counter()

    def walk(sequence, inherited_positive=False, inherited_negative=False):
        local_positive = bool(inherited_positive)
        local_negative = bool(inherited_negative)
        for action in _as_list(sequence):
            if not isinstance(action, dict):
                continue

            if "condition" in action and not any(
                key in action for key in ("service", "action", "choose", "if", "sequence")
            ):
                pos, neg = _validity_polarity(action, validity_vars)
                local_positive = local_positive or pos
                local_negative = local_negative or neg
                continue

            if "choose" in action:
                for choice in _as_list(action.get("choose")):
                    if not isinstance(choice, dict):
                        continue
                    pos, neg = _validity_polarity(
                        choice.get("conditions", choice.get("condition", [])), validity_vars
                    )
                    walk(choice.get("sequence"), local_positive or pos, local_negative or neg)
                if action.get("default") is not None:
                    walk(action.get("default"), local_positive, local_negative)
                continue

            if "if" in action:
                pos, neg = _validity_polarity(action.get("if"), validity_vars)
                walk(action.get("then"), local_positive or pos, local_negative or neg)
                if action.get("else") is not None:
                    walk(action.get("else"), local_positive, local_negative)
                continue

            if "sequence" in action and not any(key in action for key in ("service", "action")):
                walk(action.get("sequence"), local_positive, local_negative)
                continue

            if _is_physical_service(action):
                stats["physical_commands"] += 1
                if local_negative:
                    stats["negative_handled"] += 1
                elif local_positive:
                    stats["positive_gated"] += 1
                else:
                    stats["ungated"] += 1

    actions = effective.get("actions", effective.get("action", [])) if isinstance(effective, dict) else []
    walk(actions)
    return dict(stats)


def _numeric_trigger_fail_closed(effective, entity_id, node):
    triggers_on = set(node.get("triggers_on") or [])
    reads = set(node.get("reads") or [])
    if entity_id not in triggers_on or entity_id in reads:
        return False
    triggers = effective.get("triggers", effective.get("trigger", [])) if isinstance(effective, dict) else []
    for trigger in _as_list(triggers):
        if not isinstance(trigger, dict):
            continue
        platform = str(trigger.get("platform") or trigger.get("trigger") or "").lower()
        if platform != "numeric_state":
            continue
        if entity_id in set(flow._entity_ids(trigger.get("entity_id"))):
            return True
    return False


def classify_automation_v4(effective, entity_id, node):
    role = control_role(node)
    previous = base.classify_fallback_v3(effective, entity_id)
    if previous.get("level") == "strong":
        return {**previous, "role": role, "risk_relevant": role == "physical_control"}

    validity = validity_variables(effective, entity_id)
    branch_stats = _physical_branch_validity(effective, validity)

    if branch_stats.get("negative_handled", 0) > 0 and branch_stats.get("positive_gated", 0) > 0:
        return {
            "level": "strong",
            "kind": "explicit_valid_invalid_control_branches",
            "evidence_count": branch_stats["negative_handled"] + branch_stats["positive_gated"],
            "role": role,
            "risk_relevant": role == "physical_control",
            "validity_variables": sorted(validity),
            "branch_stats": branch_stats,
            "note": "Les états valides et invalides disposent de branches de contrôle explicites.",
        }

    if (
        branch_stats.get("physical_commands", 0) > 0
        and branch_stats.get("ungated", 0) == 0
        and branch_stats.get("positive_gated", 0) == branch_stats.get("physical_commands", 0)
    ):
        return {
            "level": "strong",
            "kind": "availability_gate_on_all_physical_branches",
            "evidence_count": branch_stats["positive_gated"],
            "role": role,
            "risk_relevant": role == "physical_control",
            "validity_variables": sorted(validity),
            "branch_stats": branch_stats,
            "note": "Toutes les branches de contrôle physique exigent une disponibilité valide.",
        }

    if _numeric_trigger_fail_closed(effective, entity_id, node):
        return {
            "level": "strong",
            "kind": "numeric_trigger_fail_closed",
            "evidence_count": 1,
            "role": role,
            "risk_relevant": role == "physical_control",
            "note": "Le numeric_state ne déclenche pas l'action quand la donnée n'est pas numérique.",
        }

    if role in {"observational", "helper_control"}:
        return {
            **previous,
            "role": role,
            "risk_relevant": False,
            "kind": previous.get("kind") or "non_physical_consumer",
        }

    return {**previous, "role": role, "risk_relevant": role == "physical_control"}


def build_resilience_analysis_v4(report, automation_map=None):
    critical = (report.get("architecture_analysis") or {}).get("critical_dependencies") or []
    if automation_map is None:
        automation_map, _ = effective_automation_map(report)
    graph = report.get("dependency_graph") or []
    items = []

    for dep in critical:
        entity_id = str(dep.get("entity_id") or "")
        kind = architecture_base._kind(entity_id)
        evidence = []
        users = []
        counts = Counter()
        risk_counts = Counter()

        for node in graph:
            refs = set(node.get("references") or []) | set(node.get("triggers_on") or []) | set(node.get("reads") or [])
            if entity_id not in refs:
                continue

            alias = str(node.get("automation") or "")
            users.append(alias)
            records = automation_map.get(alias) or []
            role = control_role(node)
            classification = {
                "level": "none",
                "kind": "not_uniquely_resolved",
                "role": role,
                "risk_relevant": role == "physical_control",
            }
            if len(records) == 1:
                classification = classify_automation_v4(records[0].get("effective") or {}, entity_id, node)

            level = str(classification.get("level") or "none")
            role = str(classification.get("role") or role)
            counts[(role, level)] += 1
            counts[("all", level)] += 1
            counts[("role", role)] += 1
            if classification.get("risk_relevant"):
                risk_counts[level] += 1

            evidence.append({
                "automation": alias,
                "protection": level,
                "evidence_kind": classification.get("kind", "none"),
                "role": role,
                "risk_relevant": bool(classification.get("risk_relevant")),
            })

        total = len(users)
        physical_total = counts[("role", "physical_control")]
        if kind == "helper":
            status = "configuration_dependency"
        elif physical_total == 0:
            status = "low_operational_exposure"
        elif risk_counts["none"] > 0:
            status = "review"
        elif risk_counts["weak"] > 0:
            status = "partial"
        else:
            status = "protected"

        items.append({
            "entity_id": entity_id,
            "dependency_kind": kind,
            "criticality": dep.get("criticality"),
            "automation_count": total,
            "explicit_guard_count": counts[("all", "strong")],
            "numeric_default_only_count": counts[("all", "weak")],
            "unprotected_count": risk_counts["none"],
            "strong_protection_ratio": round(risk_counts["strong"] / physical_total, 3) if physical_total else 1.0,
            "handled_or_defaulted_ratio": round((risk_counts["strong"] + risk_counts["weak"]) / physical_total, 3) if physical_total else 1.0,
            "status": status,
            "automations": users[:20],
            "automation_evidence": evidence[:30],
            "counts_as_external_spof": kind == "sensor",
            "physical_control_consumer_count": physical_total,
            "helper_control_consumer_count": counts[("role", "helper_control")],
            "observational_consumer_count": counts[("role", "observational")],
            "other_control_consumer_count": counts[("role", "other_control")],
            "unprotected_physical_automation_count": risk_counts["none"],
            "weak_physical_automation_count": risk_counts["weak"],
            "protected_physical_automation_count": risk_counts["strong"],
            "observational_unprotected_count": counts[("observational", "none")],
            "helper_unprotected_count": counts[("helper_control", "none")],
            "interpretation": (
                "V4 sépare les consommateurs physiques des usages observationnels ou helpers. "
                "Seuls les contrôles physiques non protégés alimentent le risque SPOF externe."
            ),
        })

    external_items = [item for item in items if item.get("counts_as_external_spof")]
    result = {
        "model": MODEL,
        "critical_dependency_count": len(items),
        "external_spof_count": len(external_items),
        "helper_dependency_count": sum(1 for item in items if item.get("dependency_kind") == "helper"),
        "review_count": sum(1 for item in external_items if item.get("status") == "review"),
        "partial_count": sum(1 for item in external_items if item.get("status") == "partial"),
        "protected_count": sum(1 for item in external_items if item.get("status") == "protected"),
        "low_operational_exposure_count": sum(1 for item in external_items if item.get("status") == "low_operational_exposure"),
        "configuration_dependency_count": sum(1 for item in items if item.get("status") == "configuration_dependency"),
        "not_applicable_count": sum(1 for item in items if item.get("status") == "not_applicable"),
        "numeric_default_only_count": sum(int(item.get("numeric_default_only_count", 0) or 0) for item in items),
        "unprotected_automation_count": sum(int(item.get("unprotected_physical_automation_count", 0) or 0) for item in external_items),
        "weak_physical_automation_count": sum(int(item.get("weak_physical_automation_count", 0) or 0) for item in external_items),
        "physical_control_consumer_count": sum(int(item.get("physical_control_consumer_count", 0) or 0) for item in external_items),
        "observational_consumer_count": sum(int(item.get("observational_consumer_count", 0) or 0) for item in external_items),
        "items": items[:30],
        "raw_yaml_persisted": False,
        "note": (
            "V4 tient compte du rôle métier du consommateur, des numeric_state fail-closed "
            "et des branches explicites de disponibilité avant de conclure à un SPOF."
        ),
    }
    report["resilience_analysis"] = result
    return result


def _remove_previous_recommendation(report):
    report["findings"] = [item for item in report.get("findings") or [] if str(item.get("rule_id") or "") != RULE_ID]
    report["diagnostic_explanations"] = [item for item in report.get("diagnostic_explanations") or [] if str(item.get("id") or "") != DIAGNOSTIC_ID]
    for section_name in ("action_plan", "recommendation_queue"):
        section = report.get(section_name) or {}
        section["items"] = [item for item in section.get("items") or [] if str(item.get("id") or "") != DIAGNOSTIC_ID]


def build_resilience_recommendations_v2(report):
    _remove_previous_recommendation(report)
    resilience = report.get("resilience_analysis") or {}
    candidates = []
    for item in resilience.get("items") or []:
        if not item.get("counts_as_external_spof"):
            continue
        criticality = int(item.get("criticality", 0) or 0)
        unprotected = int(item.get("unprotected_physical_automation_count", 0) or 0)
        weak = int(item.get("weak_physical_automation_count", 0) or 0)
        if criticality < 60 or (unprotected <= 0 and weak <= 0):
            continue
        candidates.append(item)
    candidates.sort(
        key=lambda item: (
            -int(item.get("unprotected_physical_automation_count", 0) or 0),
            -int(item.get("weak_physical_automation_count", 0) or 0),
            -int(item.get("criticality", 0) or 0),
            str(item.get("entity_id") or ""),
        )
    )
    top = candidates[:3]

    if not top:
        result = {
            "model": RECOMMENDATION_MODEL,
            "count": 0,
            "items": [],
            "scoring_applied": False,
            "note": (
                "Aucune dépendance externe critique n'a de contrôle physique non protégé "
                "après calibration des rôles et branches de disponibilité."
            ),
        }
        report["resilience_recommendations"] = result
        return result

    examples = []
    evidence = []
    affected = set()
    for item in top:
        risky = [
            entry for entry in item.get("automation_evidence") or []
            if entry.get("risk_relevant") and str(entry.get("protection") or "") in {"none", "weak"}
        ]
        names = [str(entry.get("automation") or "") for entry in risky if entry.get("automation")]
        affected.update(names)
        example = {
            "entity_id": item.get("entity_id"),
            "criticality": int(item.get("criticality", 0) or 0),
            "automation_count": int(item.get("automation_count", 0) or 0),
            "physical_control_consumer_count": int(item.get("physical_control_consumer_count", 0) or 0),
            "unprotected_physical_automation_count": int(item.get("unprotected_physical_automation_count", 0) or 0),
            "weak_physical_automation_count": int(item.get("weak_physical_automation_count", 0) or 0),
            "risky_automations": names[:10],
        }
        examples.append(example)
        evidence.append({
            "type": "dependency",
            "label": str(item.get("entity_id") or "Dépendance"),
            "text": (
                f"criticité {example['criticality']}/100 · "
                f"{example['unprotected_physical_automation_count']} contrôle(s) physique(s) non protégé(s) · "
                f"{example['weak_physical_automation_count']} avec fallback faible"
            ),
        })

    severity = "medium" if int(top[0].get("criticality", 0) or 0) >= 80 else "low"
    title = "Dépendance externe critique à sécuriser sur un contrôle physique"
    summary = (
        f"{len(top)} dépendance(s) externe(s) critique(s) ont encore un contrôle physique "
        "sans stratégie forte en cas de donnée invalide."
    )
    finding = {
        "rule_id": RULE_ID,
        "title": title,
        "severity": severity,
        "domain": "automations",
        "summary": summary,
        "recommendation": (
            "Ajouter une garde explicite, une branche fail-safe ou un comportement borné "
            "uniquement sur les contrôles physiques encore exposés."
        ),
        "examples": examples,
        "priority": "verify",
        "priority_label": "À vérifier",
    }
    report.setdefault("findings", []).append(finding)

    explanation = {
        "id": DIAGNOSTIC_ID,
        "source_type": "finding",
        "source_id": RULE_ID,
        "rule_id": RULE_ID,
        "title": title,
        "priority": "verify",
        "priority_label": "À vérifier",
        "severity": severity,
        "domain": "automations",
        "confidence": "high",
        "confidence_label": "Élevée",
        "confidence_score": 0.92,
        "diagnosis": summary,
        "impact": (
            "Le risque est limité aux automatisations qui utilisent la dépendance pour piloter "
            "un actionneur ou un réglage physique ; les usages purement observationnels sont exclus."
        ),
        "evidence": evidence[:10],
        "checks": [{
            "step": 1,
            "title": "Examiner le contrôle physique exposé",
            "detail": (
                f"Vérifier {examples[0]['entity_id']} dans "
                f"{', '.join(examples[0]['risky_automations'][:3]) or 'les automatisations listées'}."
            ),
        }],
        "automatic_fix": False,
        "read_only": True,
        "dependency_impact": {
            "model": RECOMMENDATION_MODEL,
            "level": "high" if severity == "medium" else "medium",
            "impacted_automation_count": len(affected),
            "impacted_automations": sorted(affected)[:20],
            "weighted_impact_score": round(sum(int(item.get("criticality", 0) or 0) for item in top) / 10.0, 2),
            "score_multiplier": 1.0,
            "scoring_applied": False,
        },
    }
    report.setdefault("diagnostic_explanations", []).append(explanation)
    action_item = {key: explanation.get(key) for key in (
        "id", "title", "priority", "priority_label", "severity", "domain",
        "confidence", "confidence_label", "confidence_score", "diagnosis", "impact",
        "source_type", "source_id", "dependency_impact",
    )}
    action_item["why_now"] = "La dépendance est critique et au moins un contrôle physique reste exposé."
    action_item["first_check"] = explanation["checks"][0]
    report.setdefault("action_plan", {}).setdefault("items", []).append(action_item)

    result = {
        "model": RECOMMENDATION_MODEL,
        "count": len(top),
        "items": examples,
        "action_plan_diagnostic_id": DIAGNOSTIC_ID,
        "scoring_applied": False,
    }
    report["resilience_recommendations"] = result
    return result
