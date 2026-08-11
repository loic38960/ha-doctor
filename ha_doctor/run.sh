#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.15.0 Trust & Publication Engine"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Single ephemeral Home Assistant state snapshot is installed as trust evidence before product analysis"
bashio::log.info "Condition Semantics V10 distinguishes numeric_state crossing events from continuous policy states"
bashio::log.info "Decision Engine V3 exposes one operational summary for fixes, logic review, watch and optimization"
bashio::log.info "Temporal V6 stages every scan as non-canonical before validation"
bashio::log.info "Publication Transaction V1 commits a score baseline only after final Self-Check and release gate"
bashio::log.info "Self-Check V7 validates the actual final Share V9 payload and can revoke a failed commit"
bashio::log.info "Assistant Share Report V9 targets 22 KiB with every finding/action identity preserved"
bashio::log.info "Blocked reports never become canonical score baselines"
bashio::log.info "No automatic Home Assistant configuration changes are performed"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v150.py
