#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.14.0 Consolidated Decision Engine"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Single ephemeral Home Assistant state snapshot remains the acquisition contract"
bashio::log.info "Consolidated pipeline removes nested 0.12/0.13 scanner wrappers"
bashio::log.info "Condition Semantics V9 analyses branch/trigger numeric policy overlap without executing templates"
bashio::log.info "Decision Engine V2 separates fix-now, logic review, restore-if-needed, watch and optimize lanes"
bashio::log.info "Registry incidents with zero automation blast radius no longer crowd the primary action lane"
bashio::log.info "Temporal V5 trusts only publication_complete canonical score snapshots"
bashio::log.info "Blocked Self-Check reports can never become score baselines"
bashio::log.info "Native Self-Check V6 validates the current contract without legacy report rewriting"
bashio::log.info "Assistant Share Report V8 targets 26 KiB and preserves decision/policy evidence"
bashio::log.info "No automatic Home Assistant configuration changes are performed"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v140.py
