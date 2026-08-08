"""HA Doctor 0.8 scanner entrypoint."""

import scanner_v050_calibration as base
import flow_v080_fixed as flow_hardening
import intelligence_v080 as intelligence

VERSION = "0.8.0"

# Use the hardened Entity Flow V3 implementation for the enrichment stage.
intelligence.enrich_dependency_graph = flow_hardening.enrich_dependency_graph


def scan(include_yaml=True):
    report = base.scan(include_yaml=include_yaml)
    report = intelligence.enrich_v080(report)
    report["version"] = VERSION
    return report
