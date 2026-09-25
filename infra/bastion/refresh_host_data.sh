#!/usr/bin/env bash
# On-demand refresh of every host-side input: Wazuh, then Greenbone.
#
# Triggered by the "Scheduled ingest" workflow's "refresh_host_data" option (through the
# SurakshaRefreshHostData SSM document), or run by hand as root on the bastion. There is no
# cron schedule: this runs only when someone asks for a fresh snapshot.
#
# The two exports are independent: if one fails the other still runs, and the script exits
# non-zero if either failed, so the failure is visible. A failed export uploads nothing, so the
# ingest simply records that scanner as unreachable.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. /etc/default/suraksha-export
export RAW_FINDINGS_BUCKET

status=0
echo "== Wazuh export"
"${here}/export_host_data.sh" || { echo "Wazuh export FAILED" >&2; status=1; }
echo "== Greenbone export"
"${here}/export_greenbone_report.sh" || { echo "Greenbone export FAILED" >&2; status=1; }
exit "${status}"
