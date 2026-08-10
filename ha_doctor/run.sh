#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.8.6"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Registry analysis uses the Home Assistant WebSocket API in read-only mode"
bashio::log.info "Single ephemeral Home Assistant state snapshot keeps one scan internally coherent"
bashio::log.info "Flow Confidence V3.1 synchronizes promoted target confidence with graph metadata"
bashio::log.info "Architecture V3 is recomputed after final flow-confidence promotion"
bashio::log.info "Controller Semantics V5 follows deterministic action branches and helper phase handoffs"
bashio::log.info "Entity Lineage V1 follows source sensors through derived template entities"
bashio::log.info "Registry Blast Radius V4 includes indirect lineage dependencies"
bashio::log.info "Temporal V3.1 separates true resolution from contextual de-escalation"
bashio::log.info "Resilience recommendations surface critical unprotected external dependencies"
bashio::log.info "Score V5 Preview V2 is usage-aware and remains non-destructive"
bashio::log.info "Consistency V5 cross-checks snapshot, architecture, summary, controllers and score projections"
bashio::log.info "Assistant Share Report V1 keeps the full report local and exports a bounded diagnostic packet"
bashio::log.info "Temporal history stores diagnostic IDs, counters, scores and timestamps only; no raw states"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v086.py
