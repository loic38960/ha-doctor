"""HA Doctor 0.8.3 scanner entrypoint.

The registry wrapper retains only affected entity identifiers (never raw state
values) so registry incidents can be correlated with the automation graph.
"""
import registry_analysis
import scanner_v082 as base
import intelligence_v083

VERSION = "0.8.3"
_MAX_AFFECTED_ENTITY_IDS = 250


def _scan_with_registry_entity_index(include_yaml=True):
    original_add = registry_analysis._add_entry
    original_finalize = registry_analysis._finalize_bucket

    def add_entry(bucket, entry, status):
        if status != "healthy" and not registry_analysis._is_optional(entry):
            entity_id = str(entry.get("entity_id") or "")
            values = bucket.setdefault("_v083_affected_entities", [])
            if entity_id and entity_id not in values and len(values) < _MAX_AFFECTED_ENTITY_IDS:
                values.append(entity_id)
        return original_add(bucket, entry, status)

    def finalize_bucket(bucket):
        result = original_finalize(bucket)
        result["affected_entities"] = list(bucket.get("_v083_affected_entities") or [])
        return result

    registry_analysis._add_entry = add_entry
    registry_analysis._finalize_bucket = finalize_bucket
    try:
        return base.scan(include_yaml=include_yaml)
    finally:
        registry_analysis._add_entry = original_add
        registry_analysis._finalize_bucket = original_finalize


def scan(include_yaml=True):
    report = _scan_with_registry_entity_index(include_yaml=include_yaml)
    report = intelligence_v083.enrich_v083(report)
    report["version"] = VERSION
    return report
