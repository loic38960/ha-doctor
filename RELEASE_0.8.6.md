# HA Doctor 0.8.6 — Compact Share Report

0.8.6 addresses a practical field issue: complete HA Doctor reports can become too large to attach reliably to a support or assistant conversation.

## What changed

- New **Assistant Share Report V1** keeps the full report local and creates a bounded diagnostic packet for sharing.
- New UI action: **Rapport à envoyer**.
- New endpoint: `/api/download-share` with filename `ha-doctor-share.json`.
- New JSON endpoint: `/api/share-report`.
- The share report keeps entity IDs, findings, action-plan diagnostics, registry incidents, controller semantics, architecture hotspots, temporal state, resilience and score context.
- It excludes the complete dependency graph, full repeated registry entity lists, raw YAML, raw states and secret values.
- Lists and examples are explicitly capped so report growth does not scale directly with the complete Home Assistant graph.
- The existing full and anonymized exports remain available and unchanged.

## Field validation

The 0.8.5 report that motivated this release was about 561 KB as an indented file. The new compact serialization of the same diagnostic content is designed to be around one fifth of that size while preserving the data needed for follow-up analysis.

## Safety

HA Doctor remains local and read-only. This release adds no configuration write, auto-fix, template execution or external AI call.
