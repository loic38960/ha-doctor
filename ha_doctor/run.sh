#!/usr/bin/with-contenv bashio
set -euo pipefail

export HA_DOCTOR_SCAN_ON_START="$(bashio::config 'scan_on_start')"
export HA_DOCTOR_YAML_ANALYSIS="$(bashio::config 'include_yaml_analysis')"

exec python3 /app/app.py
