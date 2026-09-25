#!/usr/bin/env bash
# Ask the bastion to refresh its host-side inputs (Wazuh + Greenbone -> S3 inputs/) via AWS
# Systems Manager, and wait for the result. No SSH is used, so it works from a GitHub runner
# (the bastion's security group only allows the operator's IP).
#
# Runs only the fixed SSM document SurakshaRefreshHostData, which executes
# /opt/suraksha/refresh_host_data.sh on the bastion and nothing else.
#
# Requires AWS credentials in the environment (aws-oidc-login.sh) and AWS_REGION.
set -euo pipefail

: "${AWS_REGION:?AWS_REGION is not set}"
timeout_seconds=600

instance_id=$(aws ec2 describe-instances \
  --filters Name=tag:Name,Values=loanease-bastion-scanner Name=instance-state-name,Values=running \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
[ -n "${instance_id}" ] && [ "${instance_id}" != "None" ] || { echo "no running bastion found" >&2; exit 1; }
echo "bastion: ${instance_id}"

command_id=$(aws ssm send-command \
  --document-name SurakshaRefreshHostData \
  --instance-ids "${instance_id}" \
  --comment "suraksha refresh (run ${GITHUB_RUN_ID:-manual})" \
  --query Command.CommandId --output text)
echo "ssm command: ${command_id}"

deadline=$(( $(date +%s) + timeout_seconds ))
while :; do
  status=$(aws ssm get-command-invocation --command-id "${command_id}" --instance-id "${instance_id}" \
    --query Status --output text 2>/dev/null || echo Pending)
  case "${status}" in
    Success) break ;;
    Failed|Cancelled|TimedOut|Cancelling)
      echo "::error::bastion refresh ${status}"
      aws ssm get-command-invocation --command-id "${command_id}" --instance-id "${instance_id}" \
        --query '[StandardOutputContent,StandardErrorContent]' --output text || true
      exit 1 ;;
  esac
  [ "$(date +%s)" -lt "${deadline}" ] || { echo "::error::bastion refresh timed out (last status ${status})"; exit 1; }
  sleep 5
done

aws ssm get-command-invocation --command-id "${command_id}" --instance-id "${instance_id}" \
  --query StandardOutputContent --output text
