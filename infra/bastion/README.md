# `infra/bastion/` — daily host-side export

The bastion runs the Wazuh manager, so Wazuh's alerts and agent list are only reachable
there. `export_host_data.sh` packages them and uploads `inputs/wazuh_bundle.json` to the
raw-findings bucket, where the `scheduled-ingest` workflow picks it up.

## One-time setup (on the bastion)

Prerequisite: `terraform apply` of the `pipeline` module, which attaches the
`suraksha-bastion-exporter` instance profile (PutObject on `inputs/*` only).

```bash
# 1. AWS CLI v2
curl -sS https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp && sudo /tmp/aws/install

# 2. Copy the two files (from a checkout of this repo, via scp)
sudo mkdir -p /opt/suraksha
sudo cp export_host_data.sh /opt/suraksha/ && sudo chmod 755 /opt/suraksha/export_host_data.sh
sudo cp ../inventory/build_wazuh_bundle.py /opt/suraksha/

# 3. Bucket + cron
echo 'export RAW_FINDINGS_BUCKET=loanease-raw-findings-f00321' | sudo tee /etc/default/suraksha-export
sudo cp suraksha-export.cron /etc/cron.d/suraksha-export

# 4. Test it once by hand
sudo bash -c '. /etc/default/suraksha-export && /opt/suraksha/export_host_data.sh'
aws s3 ls s3://loanease-raw-findings-f00321/inputs/    # from your laptop
```

## Greenbone is not automated here

No verified way to export a Greenbone report from inside the container stack exists yet
(gvmd publishes no port), so this job does not touch it. Upload the report by hand after a
scan, from a machine with AWS access:

```bash
aws s3 cp report.csv s3://loanease-raw-findings-f00321/inputs/greenbone_report.csv
```

The workflow accepts a Greenbone report of any age and prints how old it is, because a scan
export carries its own scan timestamps. Export it with `levels=chmlg` so Log-severity
results (where version-banner detections live) are included.
