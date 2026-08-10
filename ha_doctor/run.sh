#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.8.8"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Registry analysis uses the Home Assistant WebSocket API in read-only mode"
bashio::log.info "Single ephemeral Home Assistant state snapshot keeps one scan internally coherent"
bashio::log.info "Flow Confidence V3.1 synchronizes promoted target confidence with graph metadata"
bashio::log.info "Architecture V3 is recomputed after final flow-confidence promotion"
bashio::log.info "Controller Semantics V6 recognizes literal mode exclusivity and supervisory interlocks"
bashio::log.info "Controller Review Summary V2 separates entity counts from unresolved pair counts"
bashio::log.info "Entity Lineage V1 follows source sensors through derived template entities"
bashio::log.info "Registry Blast Radius V4 includes indirect lineage dependencies"
bashio::log.info "Temporal V3.1 separates true resolution from contextual de-escalation"
bashio::log.info "Resilience V4 separates physical controls from helper and observational consumers"
bashio::log.info "Score V5 Preview V2 remains non-destructive; primary Score V4 is unchanged"
bashio::log.info "Consistency V6 cross-checks semantic pair, role-aware resilience and final-plan identities"
bashio::log.info "Assistant Share Report V2 keeps the full report local and hard-bounds the handoff packet"
bashio::log.info "Temporal history stores diagnostic IDs, counters, scores and timestamps only; no raw states"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v088.py
