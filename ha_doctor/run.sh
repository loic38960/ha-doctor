#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.8.2"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Registry analysis uses the Home Assistant WebSocket API in read-only mode"
bashio::log.info "Single ephemeral Home Assistant state snapshot keeps one scan internally coherent"
bashio::log.info "Entity Flow V3 confidence gates now distinguish resolution from certainty"
bashio::log.info "Condition Semantics V2 separates startup reconciliation, disjoint triggers and deterministic coordination from unresolved conflicts"
bashio::log.info "Resilience V2 separates explicit invalid-state guards from weak numeric defaults"
bashio::log.info "Contextual score preview never rewrites the stable Score V4 history"
bashio::log.info "Temporal history stores diagnostic IDs, counters and aggregate scores only; no raw states"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v082.py
