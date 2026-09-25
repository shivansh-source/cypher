#!/usr/bin/env bash
# Daily export of Wazuh host data from the bastion to S3 (inputs/wazuh_bundle.json).
#
# Runs as root from cron on the Wazuh manager host (see suraksha-export.cron). Needs the AWS
# CLI and an instance profile allowing s3:PutObject on inputs/* (terraform module "pipeline").
# The bundle builder must sit next to this script: build_wazuh_bundle.py (stdlib only).
#
# What it never does: invent agent status. Status comes straight from `agent_control -l`;
# if that or the alerts file cannot be read, the script fails and uploads nothing, so the
# ingest workflow sees a missing/stale input and records Wazuh as unreachable.
set -euo pipefail

: "${RAW_FINDINGS_BUCKET:?set RAW_FINDINGS_BUCKET (see /etc/default/suraksha-export)}"
here="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

# alerts.json is the manager's current-day alert log (rotated by Wazuh at midnight), so the
# bundle holds today's alerts so far, not an unbounded history.
cp /var/ossec/logs/alerts/alerts.json "${work}/alerts.json"
/var/ossec/bin/agent_control -l >"${work}/agent-list.txt"

python3 "${here}/build_wazuh_bundle.py" \
  --alerts "${work}/alerts.json" --agents "${work}/agent-list.txt" >"${work}/wazuh_bundle.json"

aws s3 cp "${work}/wazuh_bundle.json" "s3://${RAW_FINDINGS_BUCKET}/inputs/wazuh_bundle.json" --only-show-errors
echo "$(date -u +%FT%TZ) uploaded wazuh_bundle.json ($(wc -c <"${work}/wazuh_bundle.json") bytes)"
