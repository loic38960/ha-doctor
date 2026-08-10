"""HA Doctor 0.8.6 scanner compatibility entrypoint."""
import time

import scanner_v085 as base

VERSION = "0.8.6"
REPORT_SCHEMA = "ha-doctor-report/0.8.6"


def scan(include_yaml=True):
    started = time.monotonic()
    report = base.scan(include_yaml=include_yaml)
    report["version"] = VERSION

    previous_schema = report.get("report_schema") or {}
    capabilities = list(previous_schema.get("capabilities") or [])
    for capability in (
        "assistant_share_report_v1",
        "bounded_support_export",
        "full_report_preserved_locally",
    ):
        if capability not in capabilities:
            capabilities.append(capability)
    compatible = list(previous_schema.get("backward_compatible_with") or [])
    if "0.8.5" not in compatible:
        compatible.append("0.8.5")
    report["report_schema"] = {
        **previous_schema,
        "version": REPORT_SCHEMA,
        "backward_compatible_with": compatible,
        "capabilities": capabilities,
    }

    report.setdefault("privacy", {}).update({
        "assistant_share_export_raw_states_included": False,
        "assistant_share_export_raw_yaml_included": False,
        "assistant_share_export_secret_values_included": False,
    })
    report.setdefault("diagnostic_engine", {}).update({
        "assistant_share_report_v1": True,
        "full_report_still_available": True,
    })
    report.setdefault("score_meta", {}).update({
        "delivery_version": VERSION,
        "share_report_model": "assistant_share_report_v1",
    })
    report["scan_duration_seconds"] = round(time.monotonic() - started, 3)
    return report
