#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.17.0 Resolution & Attribution Engine"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "One ephemeral Home Assistant state snapshot remains the acquisition contract"
bashio::log.info "Decision Engine V5 resolves static evidence before requesting manual review"
bashio::log.info "Automation Feedback V2 distinguishes terminating state transitions from retrigger candidates"
bashio::log.info "Duplicate Semantics V2 can promote exact side-effect duplicates to manual fix-ready"
bashio::log.info "Missing Reference Intelligence V1 classifies references without inventing replacements"
bashio::log.info "Resilience V6 emits explicit manual guard strategies and preserves must-fix vs hardening"
bashio::log.info "Temporal V8 stores published domain scores for future score attribution"
bashio::log.info "Self-Check V9 validates resolution, attribution, privacy and Share V11"
bashio::log.info "Assistant Share Report V11 targets 18 KiB and preserves every finding/action identity"
bashio::log.info "No automatic Home Assistant configuration changes are performed"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v170.py
