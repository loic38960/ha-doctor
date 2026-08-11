#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.11.0 Cross-Validated Engine"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Single ephemeral Home Assistant state snapshot remains the acquisition contract"
bashio::log.info "Controller Semantics V7 preserves unresolved physical overlap evidence"
bashio::log.info "Resilience Recommendations V3 remain exposure-first and automation-traceable"
bashio::log.info "Product Intelligence V3 derives security and maintenance counts from source findings"
bashio::log.info "Cross-Section Truth V1 prevents UI/export counters drifting from findings"
bashio::log.info "Report Self-Check V3 validates the full report and the actual support export"
bashio::log.info "Assistant Share Report V5 preserves essential controller/resilience evidence"
bashio::log.info "Score Change Trace V2 exposes the previous primary-score timestamp when available"
bashio::log.info "No automatic Home Assistant configuration changes are performed"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v110.py
