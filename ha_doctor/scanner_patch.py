"""HA Doctor 0.2.4 validation layer.

Keeps the proven 0.2.x scanner intact while adding runtime filtering based on
Home Assistant's own read-only service registry and a few targeted checks found
on the first real-world audit.
"""
import scanner as base
from rules import build_scores, finding

VERSION = "0.2.4"


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


def _technical_reference(item, known_actions):
    entity_id = str(item.get("entity_id", "")).lower() if isinstance(item, dict) else ""
    if entity_id in known_actions:
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
        # Avoid parsing hundreds of unrelated files a second time.
        if "platform: integration" not in text and "platform: 'integration'" not in text and 'platform: "integration"' not in text:
            continue
        try:
            data = base.yaml.load(text, Loader=base.HALoader)
        except Exception:
            continue
        walk(data, rel)
    return issues


def _severity_counts(findings):
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for item in findings:
        severity = item.get("severity", "info")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def scan(include_yaml=True):
    known_actions = _known_actions()
    original_scan_yaml = base._scan_yaml

    def patched_scan_yaml(live_entity_ids):
        result = original_scan_yaml(live_entity_ids)
        raw = result.get("missing_entity_references", [])
        result["missing_entity_references"] = [
            item for item in raw if not _technical_reference(item, known_actions)
        ]
        result["v024_filtered_reference_count"] = len(raw) - len(result["missing_entity_references"])
        return result

    base._scan_yaml = patched_scan_yaml
    try:
        report = base.scan(include_yaml=include_yaml)
    finally:
        base._scan_yaml = original_scan_yaml

    report["version"] = VERSION

    # Reports are meant to be shareable with support/HA Doctor. Avoid persisting
    # unnecessary identifying labels by default.
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

    report["scores"] = build_scores(report.get("findings", []))
    report["severity_counts"] = _severity_counts(report.get("findings", []))
    return report
