"""HA Doctor 0.3 diagnostic layer.

Adds customer-facing priorities, grouped entity health, calibrated scoring and
runtime filtering while keeping the proven 0.2 scanner/rules engine intact.
"""
from collections import Counter, defaultdict

import scanner as base
from rules import build_scores, finding

VERSION = "0.3.0"
STATELESS_UNKNOWN_DOMAINS = {"scene", "button", "event", "conversation", "stt", "tts"}

PRIORITY_LABELS = {
    "action_now": "À corriger maintenant",
    "verify": "À vérifier",
    "optimize": "Optimisations",
    "info": "Informations",
}
PRIORITY_ORDER = {"action_now": 0, "verify": 1, "optimize": 2, "info": 3}

RULE_PRIORITY = {
    "HD-AUTO-009": "action_now",
    "HD-AUTO-006": "action_now",
    "HD-CFG-006": "action_now",
    "HD-SEC-001": "action_now",
    "HD-CFG-001": "verify",
    "HD-CFG-002": "verify",
    "HD-CFG-004": "verify",
    "HD-ENT-001": "verify",
    "HD-ENT-002": "verify",
    "HD-ENT-003": "verify",
    "HD-AUTO-003": "verify",
    "HD-AUTO-005": "verify",
    "HD-AUTO-008": "verify",
    "HD-SEC-003": "optimize",
    "HD-AUTO-001": "optimize",
    "HD-AUTO-002": "optimize",
    "HD-AUTO-004": "info",
    "HD-AUTO-007": "optimize",
    "HD-PERF-001": "optimize",
    "HD-PERF-002": "optimize",
    "HD-CFG-003": "info",
    "HD-CFG-005": "info",
}

SCORE_PENALTY = {
    "critical": 20,
    "high": 12,
    "medium": 5,
    "low": 2,
    "info": 0,
}
SCORE_WEIGHTS = {
    "system": 0.10,
    "entities": 0.15,
    "automations": 0.35,
    "configuration": 0.15,
    "security": 0.15,
    "performance": 0.10,
}


def _known_actions():
    errors = []
    payload = base._safe_api_get("/core/api/services", errors) or []
    actions = set()
    if not isinstance(payload, list):
        return actions
    for item in payload:
        if not isinstance(item, dict):
            continue
        domain = item.get("domain")
        services = item.get("services", [])
        if not isinstance(domain, str):
            continue
        if isinstance(services, dict):
            services = list(services)
        if not isinstance(services, list):
            continue
        for service in services:
            if isinstance(service, str):
                actions.add(f"{domain}.{service}".lower())
    return actions


def _recorder_excluded_entities():
    path = base.CONFIG_ROOT / "configuration.yaml"
    if not path.exists():
        return set()
    try:
        data = base.yaml.load(path.read_text(encoding="utf-8", errors="replace"), Loader=base.HALoader)
    except Exception:
        return set()
    if not isinstance(data, dict):
        return set()
    recorder = data.get("recorder")
    if not isinstance(recorder, dict):
        return set()
    exclude = recorder.get("exclude")
    if not isinstance(exclude, dict):
        return set()
    entities = exclude.get("entities", [])
    if not isinstance(entities, list):
        entities = [entities]
    return {str(entity).lower() for entity in entities if isinstance(entity, str) and "." in entity}


def _technical_reference(item, known_actions, recorder_excluded):
    entity_id = str(item.get("entity_id", "")).lower() if isinstance(item, dict) else ""
    if entity_id in known_actions or entity_id in recorder_excluded:
        return True
    if "." in entity_id and entity_id.split(".", 1)[1] in {"yaml", "yml"}:
        return True

    locations = item.get("locations", []) if isinstance(item, dict) else []
    if locations:
        paths = [str(x.get("file", "")).replace("\\", "/").lower() for x in locations]
        if all("/blueprints/" in f"/{path}" for path in paths):
            return True
    return False


def _integration_sensor_issues():
    issues = []
    root = base.CONFIG_ROOT
    if not root.exists():
        return issues

    def walk(obj, source):
        if isinstance(obj, list):
            for item in obj:
                walk(item, source)
            return
        if not isinstance(obj, dict):
            return
        if obj.get("platform") == "integration":
            src = obj.get("source")
            if isinstance(src, str) and "." in src:
                domain = src.split(".", 1)[0].lower()
                if domain != "sensor":
                    issues.append({
                        "file": source,
                        "name": obj.get("name"),
                        "source": src.lower(),
                        "source_domain": domain,
                        "reason": "integration_source_must_be_numeric_sensor",
                    })
        for value in obj.values():
            walk(value, source)

    for path in sorted(root.rglob("*")):
        if not path.is_file() or not base._should_read(path):
            continue
        rel = str(path.relative_to(root))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "platform: integration" not in text and "platform: 'integration'" not in text and 'platform: "integration"' not in text:
            continue
        try:
            data = base.yaml.load(text, Loader=base.HALoader)
        except Exception:
            continue
        walk(data, rel)
    return issues


def _priority_for(item):
    rule_id = item.get("rule_id")
    if rule_id in RULE_PRIORITY:
        return RULE_PRIORITY[rule_id]
    severity = item.get("severity")
    if severity in {"critical", "high"}:
        return "action_now"
    if severity == "medium":
        return "verify"
    if severity == "low":
        return "optimize"
    return "info"


def _decorate_findings(findings):
    decorated = []
    for item in findings:
        item = dict(item)
        priority = _priority_for(item)
        item["priority"] = priority
        item["priority_label"] = PRIORITY_LABELS[priority]
        decorated.append(item)
    decorated.sort(key=lambda x: (
        PRIORITY_ORDER.get(x.get("priority"), 9),
        {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(x.get("severity"), 9),
        x.get("rule_id", ""),
    ))
    return decorated


def _severity_counts(findings):
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for item in findings:
        severity = item.get("severity", "info")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _priority_counts(findings):
    counts = {key: 0 for key in PRIORITY_LABELS}
    for item in findings:
        priority = item.get("priority", "info")
        counts[priority] = counts.get(priority, 0) + 1
    return counts


def _build_priority_scores(findings):
    scores = {domain: 100 for domain in SCORE_WEIGHTS}
    for item in findings:
        domain = item.get("domain")
        if domain not in scores:
            continue
        penalty = SCORE_PENALTY.get(item.get("severity"), 0)
        scores[domain] = max(0, scores[domain] - penalty)
    global_score = round(sum(scores[key] * SCORE_WEIGHTS[key] for key in SCORE_WEIGHTS))
    return {"global": global_score, "domains": scores}


def _family(entity_id):
    entity_id = str(entity_id or "").lower()
    domain = entity_id.split(".", 1)[0] if "." in entity_id else "other"
    object_id = entity_id.split(".", 1)[1] if "." in entity_id else entity_id

    mobile_markers = (
        "iphone", "ipad", "android", "mobile_app", "kiosk", "ssid", "bssid",
        "geocoded_location", "sim_", "activity_", "storage_", "connection_type",
    )
    if any(marker in object_id for marker in mobile_markers):
        return "mobile", "Mobiles / Companion App"
    if domain in {"number", "select", "text"}:
        return "device_settings", "Paramètres d'appareils"
    if domain in {"person", "device_tracker"}:
        return "presence", "Présence / localisation"
    if domain == "update":
        return "updates", "Mises à jour"
    if domain in {"sensor", "binary_sensor"}:
        return "sensors", "Capteurs"
    if domain in {"switch", "light", "cover", "climate", "fan", "water_heater", "lawn_mower", "vacuum", "lock", "alarm_control_panel"}:
        return "devices", "Appareils / actionneurs"
    return domain, domain.replace("_", " ").title()


def _group_entities(entity_ids, limit=6):
    buckets = defaultdict(list)
    labels = {}
    for entity_id in entity_ids:
        key, label = _family(entity_id)
        labels[key] = label
        buckets[key].append(entity_id)
    groups = []
    for key, values in buckets.items():
        groups.append({
            "key": key,
            "label": labels[key],
            "count": len(values),
            "examples": sorted(values)[:limit],
        })
    groups.sort(key=lambda x: (-x["count"], x["label"]))
    return groups


def _entity_health(states):
    unavailable = []
    unknown_raw = []
    unknown_stateful = []
    for state in states if isinstance(states, list) else []:
        if not isinstance(state, dict):
            continue
        entity_id = state.get("entity_id")
        current = state.get("state")
        if not isinstance(entity_id, str):
            continue
        if current == "unavailable":
            unavailable.append(entity_id)
        elif current == "unknown":
            unknown_raw.append(entity_id)
            domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
            if domain not in STATELESS_UNKNOWN_DOMAINS:
                unknown_stateful.append(entity_id)

    unavailable_groups = _group_entities(unavailable)
    unknown_groups = _group_entities(unknown_stateful)
    mobile_unavailable = next((g["count"] for g in unavailable_groups if g["key"] == "mobile"), 0)
    settings_unknown = next((g["count"] for g in unknown_groups if g["key"] == "device_settings"), 0)

    return {
        "unavailable": {
            "total": len(unavailable),
            "groups": unavailable_groups,
            "likely_transient_count": mobile_unavailable,
            "attention_count": max(0, len(unavailable) - mobile_unavailable),
        },
        "unknown": {
            "total": len(unknown_raw),
            "stateful_count": len(unknown_stateful),
            "ignored_stateless_count": len(unknown_raw) - len(unknown_stateful),
            "groups": unknown_groups,
            "likely_optional_count": settings_unknown,
            "attention_count": max(0, len(unknown_stateful) - settings_unknown),
        },
    }


def _diagnostic_summary(findings):
    counts = _priority_counts(findings)
    top_actions = [
        {
            "rule_id": item.get("rule_id"),
            "title": item.get("title"),
            "severity": item.get("severity"),
            "domain": item.get("domain"),
        }
        for item in findings if item.get("priority") == "action_now"
    ][:5]
    return {
        "priority_counts": counts,
        "actionable_count": counts.get("action_now", 0) + counts.get("verify", 0),
        "top_actions": top_actions,
        "headline": (
            f"{counts.get('action_now', 0)} correction(s) prioritaire(s), "
            f"{counts.get('verify', 0)} point(s) à vérifier et "
            f"{counts.get('optimize', 0)} optimisation(s)."
        ),
    }


def scan(include_yaml=True):
    known_actions = _known_actions()
    recorder_excluded = _recorder_excluded_entities()
    original_scan_yaml = base._scan_yaml

    def patched_scan_yaml(live_entity_ids):
        result = original_scan_yaml(live_entity_ids)
        raw = result.get("missing_entity_references", [])
        result["missing_entity_references"] = [
            item for item in raw
            if not _technical_reference(item, known_actions, recorder_excluded)
        ]
        result["filtered_reference_count"] = len(raw) - len(result["missing_entity_references"])
        return result

    base._scan_yaml = patched_scan_yaml
    try:
        report = base.scan(include_yaml=include_yaml)
    finally:
        base._scan_yaml = original_scan_yaml

    report["version"] = VERSION
    report.get("home_assistant", {}).pop("location_name", None)
    report.get("host", {}).pop("hostname", None)

    issues = _integration_sensor_issues() if include_yaml else []
    report.setdefault("diagnostics", {})["integration_sensor_issues"] = issues
    if issues:
        report.setdefault("findings", []).append(finding(
            "HD-CFG-006",
            "Capteur Integral branché sur une source non numérique",
            "medium",
            "configuration",
            f"{len(issues)} capteur(s) `integration` utilisent une source qui n'est pas un sensor numérique.",
            "Le helper Integral attend un sensor numérique. Pour mesurer une durée ON/OFF, utiliser plutôt history_stats ou un capteur numérique adapté.",
            examples=issues[:10],
        ))

    legacy_scores = build_scores(report.get("findings", []))
    findings = _decorate_findings(report.get("findings", []))
    report["findings"] = findings
    report["scores"] = _build_priority_scores(findings)
    report["score_meta"] = {
        "model": "priority_v1",
        "alpha": True,
        "legacy_global": legacy_scores.get("global"),
        "note": "Indice de santé alpha : les priorités client comptent davantage que le volume brut d'alertes.",
    }
    report["severity_counts"] = _severity_counts(findings)
    report["diagnostic_summary"] = _diagnostic_summary(findings)

    state_errors = []
    states = base._safe_api_get("/core/api/states", state_errors) or []
    report["entity_health"] = _entity_health(states)
    if state_errors:
        report.setdefault("diagnostics", {})["entity_health_api_errors"] = state_errors

    report.setdefault("privacy", {})["entity_health_raw_states_persisted"] = False
    return report
