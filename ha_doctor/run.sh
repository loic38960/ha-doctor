#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.5.0"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Registry analysis uses the Home Assistant WebSocket API in read-only mode"
bashio::log.info "Explanatory diagnostic engine runs locally without external AI"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app.py
