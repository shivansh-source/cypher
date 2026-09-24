# `infra/terraform/` — LoanEase sandbox

Terraform for the deliberately vulnerable AWS sandbox whose telemetry Su₹aksha
ingests. It exists to generate real, verifiable findings (Prowler, PMapper,
Wazuh, Greenbone) for the connectors in `infra/connectors/`; it is not part of
the risk engine. `manifest.yaml` is the ground truth of what was planted (V-01
to V-06) and how each item was verified.

```
environments/dev/   backend.tf, main.tf, variables.tf, outputs.tf, .terraform.lock.hcl
modules/network/    VPC 10.20.0.0/16, one public subnet, no NAT
modules/compute/    4 instances (portal, bastion+scanner, db, endpoint-sim) + bootstrap scripts
modules/iam/        V-03 role, V-04 user, V-05 user+key
modules/backup/     V-06 DLM policy
```

## State lives in S3, not in this repo

`environments/dev/backend.tf` points at `s3://loanease-tfstate-d07f64/dev/terraform.tfstate`
(ap-south-1, native lockfile). State is keyed by that bucket and key, not by
the directory, so moving this code did not move or change the state.
Never commit `*.tfstate*`, `tfplan`, or `terraform.tfvars` (all gitignored).

## Use

```
cd infra/terraform/environments/dev
export AWS_PROFILE=loanease-sandbox
echo "my_ip_cidr = \"$(curl -s checkip.amazonaws.com)/32\"" > terraform.tfvars   # re-run when your IP changes
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

`terraform init` must be re-run in a fresh checkout (`.terraform/` is not
committed). Public IPs change on every stop/start; re-read `terraform output`.

## Known fragility (manual changes not captured here)

- Wazuh's vulnerability-detection module was disabled by hand on the live
  bastion (`/var/ossec/etc/ossec.conf`) because it downloaded a 16 GB feed with
  nowhere to send results. A rebuilt bastion will regress to that.
- No auto-stop exists: instances bill continuously while running.
- The account is on the AWS Free Plan with an 8 vCPU limit, so do not add a
  fifth instance without stopping one.
