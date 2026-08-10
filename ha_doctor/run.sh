#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.10.0 Engine Candidate"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Single ephemeral Home Assistant state snapshot remains the acquisition contract"
bashio::log.info "Entity Flow V3.1 keeps 100% deterministic/dynamic target accounting"
bashio::log.info "Controller Semantics V7 explains unresolved physical overlaps without false PASS"
bashio::log.info "Resilience Recommendations V3 prioritize real unprotected physical exposure"
bashio::log.info "Product Intelligence V2 adds evidence tiers, risk breakdowns and doctor modes"
bashio::log.info "Entity Noise V1 compresses unavailable/unknown into actionable causes"
bashio::log.info "Score Projection V2 estimates 1/3/5/10-fix horizons without mutating Score V4"
bashio::log.info "Report Self-Check V2 validates cross-contract metadata and ranking invariants"
bashio::log.info "Assistant Share Report V4 uses one central 28/32 KiB contract"
bashio::log.info "Scan Performance V1 exposes phase timings and the slowest phase"
bashio::log.info "No automatic Home Assistant configuration changes are performed"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v100.py
