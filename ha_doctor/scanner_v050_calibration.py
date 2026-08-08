from collections import Counter

import diagnostic_explain as dx
import scanner_v050 as base

VERSION = "0.5.0"
LOCAL_LOGIC = {
    "automation", "script", "template", "person", "counter", "group",
    "input_boolean", "input_datetime", "input_number", "input_select",
    "input_text", "scene", "timer", "homeassistant",
}
NO_CLUSTER = {"mqtt"}


def _sort(items):
    return sorted(items, key=lambda x: (
        dx.PRIORITY_ORDER.get(x.get("priority"), 9),
        dx.SEVERITY_ORDER.get(x.get("severity"), 9),
        dx.CONFIDENCE_ORDER.get(x.get("confidence"), 9),
        -float(x.get("confidence_score", 0) or 0),
        x.get("title", ""),
    ))


def calibrate(report):
    items = list(report.get("diagnostic_explanations") or [])
    registry = report.get("registry_analysis") or {}
    clusters = {
        str(x.get("source_id")) for x in items
        if x.get("source_type") == "registry_cluster" and x.get("source_id")
    }
    kept = []
    suppressed = 0
    for item in items:
        kind = item.get("source_type")
        source = str(item.get("source_id") or "")
        if kind == "registry_integration" and source in LOCAL_LOGIC:
            suppressed += 1
            continue
        if kind == "registry_integration" and source in clusters:
            suppressed += 1
            continue
        if kind == "registry_cluster" and source in NO_CLUSTER:
            suppressed += 1
            continue
        kept.append(item)

    if registry.get("available"):
        platform_statuses = dx._platform_status_map(registry)
        existing = {x.get("id") for x in kept}
        for device in ((registry.get("device_health") or {}).get("groups") or []):
            platforms = {str(x) for x in (device.get("platforms") or []) if x}
            if not platforms.intersection(NO_CLUSTER):
                continue
            incident = dx._device_incident(device, platform_statuses, clustered_platforms=set())
            if incident and incident.get("id") not in existing:
                kept.append(incident)
                existing.add(incident.get("id"))

    kept = _sort(kept)
    report["diagnostic_explanations"] = kept[:40]
    report["action_plan"] = dx.build_action_plan(kept)
    report["executive_summary"] = dx.build_executive_summary(
        report, kept, report.get("registry_observations") or []
    )
    engine = dict(report.get("diagnostic_engine") or {})
    engine["explanation_count"] = len(kept)
    engine["confidence_counts"] = dict(Counter(x.get("confidence") for x in kept))
    engine["root_cause_calibration"] = "root_cause_v1"
    engine["suppressed_noise_count"] = suppressed
    report["diagnostic_engine"] = engine
    return report


def scan(include_yaml=True):
    report = base.scan(include_yaml=include_yaml)
    report = calibrate(report)
    report["version"] = VERSION
    return report
