# `infra/bastion/` — on-demand host-side export

The bastion runs the Wazuh manager and the Greenbone stack, so their data is only reachable
there. These scripts package it and upload it to the raw-findings bucket's `inputs/` folder,
where the `Scheduled ingest` workflow picks it up.

**There is no cron on the bastion.** The GitHub workflow triggers the refresh through AWS
Systems Manager (no SSH):

1. **Every daily run** of *Scheduled ingest* refreshes first. On a schedule a bastion failure is
   tolerated, so it never blocks the daily snapshot (stale Wazuh data is then dropped honestly).
2. **On demand (the "button"):** Actions → *Scheduled ingest* → *Run workflow* → tick
   **refresh_host_data**. A manual run fails loudly if the refresh fails.
3. **By hand on the bastion:** `sudo /opt/suraksha/refresh_host_data.sh`.

| Script | What it does |
|---|---|
| `refresh_host_data.sh` | Runs the two exports below; one failing does not stop the other, and the exit code reports it. |
| `export_host_data.sh` | Wazuh: current-day `alerts.json` + `agent_control -l` → `inputs/wazuh_bundle.json`. |
| `export_greenbone_report.sh` | Greenbone: latest report of task `loanease-full-scan`, all severities (`levels=chmlg`), through the `gvm-tools` container's gvmd socket → `inputs/greenbone_report.xml`. It exports an existing report; it does **not** start a scan. |

A failed export uploads nothing, so the ingest records that scanner as unreachable instead of
presenting missing data as clean.

## One-time setup

Prerequisites: `terraform apply` of the `pipeline` module (adds the SSM document, the bastion's
SSM permission, and the GitHub role's narrow permission to run only that document on this
instance). The bastion's SSM agent is already running.

On the bastion:

```bash
# 1. AWS CLI v2
sudo apt-get install -y unzip
curl -sS https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp && sudo /tmp/aws/install

# 2. The scripts (copy from a checkout of this repo, e.g. with scp)
sudo mkdir -p /opt/suraksha
sudo cp export_host_data.sh export_greenbone_report.sh refresh_host_data.sh /opt/suraksha/
sudo cp ../inventory/build_wazuh_bundle.py /opt/suraksha/
sudo chmod 755 /opt/suraksha/*.sh

# 3. Bucket name
echo 'RAW_FINDINGS_BUCKET=loanease-raw-findings-f00321' | sudo tee /etc/default/suraksha-export

# 4. Greenbone login for the export (never commit or paste this)
sudo install -m 600 /dev/null /opt/suraksha/gvm.pass
sudo sh -c 'cat > /opt/suraksha/gvm.pass'     # type the password, then Ctrl-D

# 5. Test once by hand
sudo /opt/suraksha/refresh_host_data.sh
```

Then check from anywhere with AWS access:

```bash
aws s3 ls s3://loanease-raw-findings-f00321/inputs/ --human-readable
```

## Notes

- `alerts.json` is Wazuh's current-day log (it rotates at midnight UTC), so a refresh captures
  today's alerts so far.
- `GREENBONE_USERNAME` defaults to `admin`; `GREENBONE_TASK_NAME`, `GREENBONE_REPORT_FILTER`
  and `GREENBONE_PASSWORD_FILE` can be overridden in `/etc/default/suraksha-export`.
- The Greenbone export can only be as fresh as Greenbone's last scan. Findings carry their own
  scan timestamps, so the snapshot shows how old they are.
