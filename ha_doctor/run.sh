#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Starting HA Doctor 0.9.0"
bashio::log.info "Read-only Home Assistant configuration mount: /ha_config"
bashio::log.info "Registry analysis uses the Home Assistant WebSocket API in read-only mode"
bashio::log.info "Single ephemeral Home Assistant state snapshot keeps one scan internally coherent"
bashio::log.info "Entity Flow V3.1 resolves deterministic and dynamic controls"
bashio::log.info "Controller Semantics V6 recognizes mode exclusivity and supervisory interlocks"
bashio::log.info "Entity Lineage V1 and Registry Blast Radius V4 correlate indirect dependencies"
bashio::log.info "Temporal V3.1 separates true resolution from contextual de-escalation"
bashio::log.info "Resilience V4 separates physical controls from helper and observational consumers"
bashio::log.info "Product Triage V1 ranks customer actions by risk, confidence, impact and fix gain"
bashio::log.info "Diagnostic Trust V1 exposes how trustworthy the current scan is"
bashio::log.info "Report Self-Check V1 validates cross-section identities before presentation"
bashio::log.info "Assistant Share Report V3 is identity-preserving and hard-bounded"
bashio::log.info "Human-readable Markdown support summary is available locally"
bashio::log.info "Score V5 remains a preview; primary Score V4 is unchanged"
bashio::log.info "No automatic Home Assistant configuration changes are performed"

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

bashio::log.info "scan_on_start=${HA_DOCTOR_SCAN_ON_START}, include_yaml_analysis=${HA_DOCTOR_YAML_ANALYSIS}"
exec python3 -u /app/app_v090.py
