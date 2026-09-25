#!/usr/bin/env bash
# Exchange this workflow run's GitHub OIDC token for short-lived AWS credentials and
# export them to later steps. Uses only curl, jq and the AWS CLI (all preinstalled on
# ubuntu runners) so the workflow needs no third-party action.
#
# Requires: `permissions: id-token: write`, and AWS_ROLE_ARN / AWS_REGION in the environment.
set -euo pipefail

: "${AWS_ROLE_ARN:?AWS_ROLE_ARN repository variable is not set}"
: "${AWS_REGION:?AWS_REGION is not set}"

token=$(curl -sS --fail \
  -H "Authorization: bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
  "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=sts.amazonaws.com" | jq -r '.value')
echo "::add-mask::${token}"

# Print the claims AWS will check against the role's trust policy (issuer, audience, subject,
# ref). They identify the run, not authenticate it, so they are safe to log; the token itself
# stays masked. An AccessDenied below almost always means `sub` differs from the trust rule.
claims=$(printf '%s' "${token}" | python3 -c '
import base64, json, sys
payload = sys.stdin.read().split(".")[1]
payload += "=" * (-len(payload) % 4)
c = json.loads(base64.urlsafe_b64decode(payload))
print({k: c.get(k) for k in ("iss", "aud", "sub", "ref", "event_name")})
')
echo "OIDC token claims: ${claims}"

creds=$(aws sts assume-role-with-web-identity \
  --role-arn "${AWS_ROLE_ARN}" \
  --role-session-name "suraksha-ingest-${GITHUB_RUN_ID}" \
  --web-identity-token "${token}" \
  --duration-seconds 3600 \
  --query Credentials --output json)

access_key=$(jq -r '.AccessKeyId' <<<"${creds}")
secret_key=$(jq -r '.SecretAccessKey' <<<"${creds}")
session_token=$(jq -r '.SessionToken' <<<"${creds}")
echo "::add-mask::${secret_key}"
echo "::add-mask::${session_token}"

{
  echo "AWS_ACCESS_KEY_ID=${access_key}"
  echo "AWS_SECRET_ACCESS_KEY=${secret_key}"
  echo "AWS_SESSION_TOKEN=${session_token}"
  echo "AWS_DEFAULT_REGION=${AWS_REGION}"
} >>"${GITHUB_ENV}"

echo "Assumed ${AWS_ROLE_ARN}"
