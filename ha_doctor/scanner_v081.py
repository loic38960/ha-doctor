"""HA Doctor 0.8.1 scanner entrypoint.

Uses one ephemeral /api/states snapshot for the complete scan, then destroys the
cache. Raw states are never written to the report or temporal history.
"""

import copy

import scanner as core_scanner
import scanner_v050_calibration as base
import flow_v080_fixed as flow_hardening
import intelligence_v080 as intelligence_v080
import intelligence_v081 as intelligence_v081

VERSION = "0.8.1"

# Keep the hardened Entity Flow V3 implementation used by 0.8.0.
intelligence_v080.enrich_dependency_graph = flow_hardening.enrich_dependency_graph


def scan(include_yaml=True):
    original_safe_get = core_scanner._safe_api_get
    state_cache = {}
    state_requests = 0

    def cached_safe_get(path, errors):
        nonlocal state_requests
        if path != "/core/api/states":
            return original_safe_get(path, errors)
        state_requests += 1
        if path not in state_cache:
            state_cache[path] = original_safe_get(path, errors)
        return copy.deepcopy(state_cache[path])

    core_scanner._safe_api_get = cached_safe_get
    try:
        report = base.scan(include_yaml=include_yaml)
        report = intelligence_v080.enrich_v080(report)
        states = state_cache.get("/core/api/states")
        report = intelligence_v081.enrich_v081(
            report,
            states_snapshot=states if isinstance(states, list) else [],
        )
        report.setdefault("scan_consistency", {})["state_api_requests_collapsed"] = state_requests
        report["scan_consistency"]["state_api_network_reads"] = 1 if state_cache else 0
        report["version"] = VERSION
        return report
    finally:
        core_scanner._safe_api_get = original_safe_get
        state_cache.clear()
