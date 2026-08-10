#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.8.1"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Registry analysis uses the Home Assistant WebSocket API in read-only mode"
bashio::log.info "Single ephemeral Home Assistant state snapshot keeps one scan internally coherent"
bashio::log.info "Entity Flow V3 confidence bands separate resolved targets from certainty"
bashio::log.info "Condition Semantics V1 removes only controller conflicts with proven state exclusivity"
bashio::log.info "Transitive script/scene call graph and critical-dependency resilience diagnostics are enabled"
bashio::log.info "Operational context can de-escalate solar-at-night and seasonal-heating observations without rewriting the health-score history"
bashio::log.info "Temporal history stores diagnostic IDs, counters and aggregate scores only; no raw states"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v081.py
