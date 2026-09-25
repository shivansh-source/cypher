#!/usr/bin/env bash
# Download one pipeline input from S3 and report its age, or fail if it is missing/stale.
#
#   fetch-input.sh <s3-key> <dest-file> <max-age-hours>
#
# max-age-hours 0 means "any age" (used for the manually-exported Greenbone report, whose
# own findings carry their scan timestamp). A missing or over-age input exits non-zero and
# the workflow then leaves that connector's *_EXPORT_PATH unset, so ingest records the
# scanner as unreachable instead of presenting stale data as current.
set -euo pipefail

key="$1"
dest="$2"
max_age_hours="$3"
: "${RAW_FINDINGS_BUCKET:?RAW_FINDINGS_BUCKET is not set}"

if ! last_modified=$(aws s3api head-object --bucket "${RAW_FINDINGS_BUCKET}" --key "${key}" \
  --query LastModified --output text 2>/dev/null); then
  echo "MISSING ${key}"
  exit 1
fi

age_hours=$(( ( $(date -u +%s) - $(date -u -d "${last_modified}" +%s) ) / 3600 ))
echo "${key}: last modified ${last_modified} (${age_hours}h ago)"

if [ "${max_age_hours}" -gt 0 ] && [ "${age_hours}" -gt "${max_age_hours}" ]; then
  echo "STALE ${key}: ${age_hours}h old, limit ${max_age_hours}h"
  exit 1
fi

aws s3 cp "s3://${RAW_FINDINGS_BUCKET}/${key}" "${dest}" --only-show-errors
