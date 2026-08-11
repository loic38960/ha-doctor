#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.13.0 Decision Engine"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Single ephemeral Home Assistant state snapshot remains the acquisition contract"
bashio::log.info "Condition Semantics V8 resolves controllers only with mandatory literal guard proof"
bashio::log.info "Decision Engine V1 turns every final diagnostic into an evidence-first manual playbook"
bashio::log.info "Entity Attention V2 prioritizes operational impact over raw unavailable/unknown counts"
bashio::log.info "Temporal Truth keeps published_primary_score_v1 and stamps truthful 0.13 metadata"
bashio::log.info "Controller Review V4 exposes remaining physical pairs and guard-matrix evidence"
bashio::log.info "Report Self-Check V5 validates decisions, playbooks, V8 proofs, Share V7 and history metadata"
bashio::log.info "Assistant Share Report V7 keeps the 28/32 KiB support contract"
bashio::log.info "No automatic Home Assistant configuration changes are performed"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v130.py
