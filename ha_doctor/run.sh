#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.12.0 Temporal Truth Engine"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Single ephemeral Home Assistant state snapshot remains the acquisition contract"
bashio::log.info "Temporal V4 stores the final published primary score under an explicit canonical history contract"
bashio::log.info "Legacy pre-0.12 score snapshots are never guessed and cannot create false stable deltas"
bashio::log.info "Public Contract Truth synchronizes action-plan, controller-review, temporal and diagnostic source identities"
bashio::log.info "Controller Evidence keeps V7 overlap proof with version-neutral customer-facing summaries"
bashio::log.info "Cross-Validated Security and Maintenance source counts remain enforced"
bashio::log.info "Exposure First resilience trace remains preserved in support exports"
bashio::log.info "Report Self-Check V4 validates full report, canonical history and Share V6"
bashio::log.info "Assistant Share Report V6 keeps the 28/32 KiB contract and preserves temporal truth"
bashio::log.info "No automatic Home Assistant configuration changes are performed"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v120.py
