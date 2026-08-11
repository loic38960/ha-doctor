"""HA Doctor 0.17 missing-reference intelligence.

Classifies HD-CFG-001 evidence without guessing replacements. It extracts entity
IDs and source-path hints from the finding evidence, then separates archive/test
references, low-impact references and runtime-relevant references. HA Doctor
never invents a replacement entity_id.
"""

import json
import re
from contracts_v170 import REFERENCE_MODEL

ENTITY_RE = re.compile(r"\b[a-z_][a-z0-9_]*\.[a-z0-9_]+\b", re.I)
_ARCHIVE_PARTS = ("archive", "backup", ".bak", "old", "disabled", "trash")


def _finding(report, rule_id):
    for item in report.get("findings") or []:
        if isinstance(item, dict) and str(item.get("rule_id") or "") == rule_id:
            return item
    return {}


def _dump(value):
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _extract_rows(finding):
    evidence = finding.get("examples") or finding.get("evidence") or finding.get("details") or []
    if not isinstance(evidence, list):
        evidence = [evidence] if evidence else []
    rows = []
    for raw in evidence:
        text = _dump(raw)
        ids = sorted(set(x.lower() for x in ENTITY_RE.findall(text)))
        source = None
        if isinstance(raw, dict):
            for key in ("file", "source", "path", "yaml_file", "location"):
                if raw.get(key):
                    source = str(raw.get(key)); break
        for entity_id in ids:
            rows.append({"entity_id": entity_id, "source": source, "raw_kind": type(raw).__name__})
    # Some finding implementations expose a direct references/list field.
    for key in ("references", "missing_references", "entity_ids"):
        for raw in finding.get(key) or []:
            if isinstance(raw, str) and ENTITY_RE.fullmatch(raw.strip()):
                rows.append({"entity_id": raw.strip().lower(), "source": None, "raw_kind": key})
    dedup = {}
    for row in rows:
        dedup[(row["entity_id"], row.get("source"))] = row
    return list(dedup.values())


def _impact_map(report):
    result = {}
    for action in (report.get("action_plan") or {}).get("items") or []:
        if not isinstance(action, dict) or str(action.get("source_id") or "") != "HD-CFG-001":
            continue
        dep = action.get("dependency_impact") or {}
        result["finding"] = {
            "level": str(dep.get("level") or "none"),
            "impacted_automation_count": int(dep.get("impacted_automation_count", 0) or 0),
        }
    return result


def build_missing_reference_intelligence(report):
    finding = _finding(report, "HD-CFG-001")
    rows = _extract_rows(finding)
    impact = (_impact_map(report).get("finding") or {})
    default_impact = int(impact.get("impacted_automation_count", 0) or 0)

    classified = []
    for row in rows:
        source = str(row.get("source") or "").lower()
        if source and any(part in source for part in _ARCHIVE_PARTS):
            classification = "archive_or_inactive_reference"
            review = "low"
        elif default_impact <= 0:
            classification = "runtime_missing_low_operational_impact"
            review = "low"
        else:
            classification = "runtime_missing_used_by_automation"
            review = "medium"
        classified.append({
            **row, "classification": classification, "review_priority": review,
            "replacement_suggestion": None, "replacement_inferred": False,
        })

    total = len({x.get("entity_id") for x in classified if x.get("entity_id")})
    result = {
        "model": REFERENCE_MODEL,
        "finding_present": bool(finding),
        "evidence_entity_count": total,
        "runtime_relevant_count": sum(1 for x in classified if x.get("classification") == "runtime_missing_used_by_automation"),
        "low_impact_count": sum(1 for x in classified if x.get("classification") == "runtime_missing_low_operational_impact"),
        "archive_or_inactive_count": sum(1 for x in classified if x.get("classification") == "archive_or_inactive_reference"),
        "items": classified[:30],
        "finding_dependency_impact": impact,
        "replacement_inference_enabled": False,
        "note": "HA Doctor classe la référence mais n'invente jamais un entity_id de remplacement.",
        "read_only": True,
    }
    report["missing_reference_intelligence"] = result
    return result
