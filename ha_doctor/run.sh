#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.16.1 Evidence Precision Engine hotfix"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "One ephemeral Home Assistant state snapshot remains the acquisition contract"
bashio::log.info "Controller Impact V2 scopes priority to unresolved physical pairs only"
bashio::log.info "Resilience V5 separates unprotected pre-control exposure from weak hardening exposure"
bashio::log.info "Repair Playbook V4 identity is normalized before Self-Check publication gating"
bashio::log.info "Decision Engine V4 uses one canonical order across report, Doctor View and support export"
bashio::log.info "Temporal V7 exposes the latest published baseline even before it is eligible for a delta"
bashio::log.info "Publication Transaction V1 still gates canonical score history"
bashio::log.info "Self-Check V8 validates exact scope, canonical order, precision evidence and compact Share V10"
bashio::log.info "Assistant Share Report V10 targets 20 KiB and preserves all finding/action identities"
bashio::log.info "No automatic Home Assistant configuration changes are performed"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v160.py
