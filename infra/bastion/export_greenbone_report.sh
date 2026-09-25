#!/usr/bin/env bash
# Export the newest Greenbone report (all severities, including Log) to S3 inputs/.
#
# Runs ON the Greenbone host (the bastion), as root. gvmd publishes no TCP port, so this goes
# through the gvm-tools container that shares gvmd's unix socket (/run/gvmd), then uploads the
# report XML to s3://$RAW_FINDINGS_BUCKET/inputs/greenbone_report.xml, which
# greenbone_connector.py reads (via GREENBONE_EXPORT_PATH) in the ingest workflow.
#
# It exports what Greenbone already has: the latest report of the named task. It does NOT start
# a scan. Log-severity results (where version-banner detections live, e.g. V-01/V-02) are kept by
# the `levels=chmlg` filter; GSA's default filter drops them.
#
# It never fabricates data: no task, no report, or a report with no results => it fails and
# uploads nothing, so the ingest records Greenbone as unreachable instead of "clean".
#
# Settings (env, all optional except the bucket):
#   RAW_FINDINGS_BUCKET         required
#   GREENBONE_COMPOSE_FILE      default /home/ubuntu/greenbone-community-edition/compose.yaml
#   GREENBONE_TASK_NAME         default loanease-full-scan
#   GREENBONE_USERNAME          default admin
#   GREENBONE_PASSWORD_FILE     default /opt/suraksha/gvm.pass   (root-only file holding the password)
#   GREENBONE_REPORT_FILTER     default "apply_overrides=0 levels=chmlg min_qod=70 first=1 rows=-1"
set -euo pipefail

: "${RAW_FINDINGS_BUCKET:?set RAW_FINDINGS_BUCKET (see /etc/default/suraksha-export)}"
compose="${GREENBONE_COMPOSE_FILE:-/home/ubuntu/greenbone-community-edition/compose.yaml}"
task_name="${GREENBONE_TASK_NAME:-loanease-full-scan}"
gvm_user="${GREENBONE_USERNAME:-admin}"
pass_file="${GREENBONE_PASSWORD_FILE:-/opt/suraksha/gvm.pass}"
report_filter="${GREENBONE_REPORT_FILTER:-apply_overrides=0 levels=chmlg min_qod=70 first=1 rows=-1}"

[ -r "${pass_file}" ] || { echo "cannot read ${pass_file}" >&2; exit 1; }
gvm_password="$(cat "${pass_file}")"

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

# One GMP request through the gvmd socket. -T: no TTY, so output is clean under cron/SSM.
gmp() {
  docker compose -f "${compose}" run --rm -T gvm-tools gvm-cli \
    --gmp-username "${gvm_user}" --gmp-password "${gvm_password}" \
    socket --socketpath /run/gvmd/gvmd.sock --xml "$1"
}

# 1. The newest report of the task.
gmp "<get_tasks filter=\"name=${task_name}\"/>" >"${work}/tasks.xml"
report_id="$(python3 - "${work}/tasks.xml" <<'PY'
import sys
import xml.etree.ElementTree as ET  # local, trusted gvmd output
root = ET.parse(sys.argv[1]).getroot()
if root.get("status", "200") != "200":
    sys.exit("gvmd refused get_tasks: " + str(root.get("status_text")))
report = root.find("./task/last_report/report")
print(report.get("id") if report is not None else "")
PY
)"
[ -n "${report_id}" ] || { echo "task '${task_name}' has no report yet" >&2; exit 1; }

# 2. That report, with every severity level (native XML, all results, no pagination).
gmp "<get_reports report_id=\"${report_id}\" details=\"1\" ignore_pagination=\"1\" filter=\"${report_filter}\"/>" \
  >"${work}/report.xml"

# 3. Refuse to publish a report that could be read as "scanned and found nothing".
results="$(python3 - "${work}/report.xml" <<'PY'
import sys
import xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
if root.get("status", "200") != "200":
    sys.exit("gvmd refused get_reports: " + str(root.get("status_text")))
print(sum(1 for _ in root.iter("result")))
PY
)"
[ "${results}" -gt 0 ] || { echo "report ${report_id} has no results; not uploading" >&2; exit 1; }

aws s3 cp "${work}/report.xml" "s3://${RAW_FINDINGS_BUCKET}/inputs/greenbone_report.xml" --only-show-errors
echo "$(date -u +%FT%TZ) uploaded greenbone_report.xml (report ${report_id}, ${results} results)"
