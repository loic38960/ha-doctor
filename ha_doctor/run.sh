#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.8.3"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Registry analysis uses the Home Assistant WebSocket API in read-only mode"
bashio::log.info "Single ephemeral Home Assistant state snapshot keeps one scan internally coherent"
bashio::log.info "Temporal V3 requires real elapsed time before promoting persistence; rapid rescans are neutralized"
bashio::log.info "Registry Blast Radius V3 correlates integration/device incidents with affected automations"
bashio::log.info "Flow Confidence V3 separates inferred targets from genuinely heuristic targets"
bashio::log.info "Condition Semantics V3 prioritizes physical actuator conflicts over helper fan-out"
bashio::log.info "Resilience V3 separates external SPOFs from internal configuration helpers"
bashio::log.info "Score V5 is preview-only; stable Score V4 history remains untouched"
bashio::log.info "Internal Consistency V3 verifies plan, queue, registry counts, score math, privacy and versions"
bashio::log.info "Temporal history stores diagnostic IDs, counters, scores and timestamps only; no raw states"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v083.py
