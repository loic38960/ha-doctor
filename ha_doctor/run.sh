#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.8.0"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Registry analysis uses the Home Assistant WebSocket API in read-only mode"
bashio::log.info "Root-cause, temporal, regression and architecture diagnostics run locally without external AI"
bashio::log.info "Entity Flow V3 resolves static and dynamic action targets without evaluating Jinja"
bashio::log.info "Script/scene calls are separated from physical controls"
bashio::log.info "Automation coverage V2 excludes unavailable registry leftovers from the coverage gap"
bashio::log.info "Maintenance Debt V2 de-duplicates weak registry signals and coverage debt"
bashio::log.info "Temporal history stores diagnostic IDs, counters and aggregate scores only; no raw states"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v080.py
