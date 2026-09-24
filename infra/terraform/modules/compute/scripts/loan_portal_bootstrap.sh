#!/bin/bash
set -euxo pipefail
exec > >(tee -a /var/log/loanease-bootstrap.log) 2>&1
export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get install -y python3-venv python3-pip

id portal >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin portal
mkdir -p /opt/loanease
cd /opt/loanease

# Versions come from the V-01 entry in manifest.yaml. Keep the two in sync.
cat > requirements.txt <<'REQ'
Flask==${flask_version}
Werkzeug==${werkzeug_version}
REQ

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# Placeholder app. debug stays False on purpose.
cat > app.py <<'APP'
from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/")
def index():
    return "<h1>LoanEase Portal</h1><p>Sandbox placeholder.</p>"


@app.route("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=False)
APP

chown -R portal:portal /opt/loanease

cat > /etc/systemd/system/loanease-portal.service <<'UNIT'
[Unit]
Description=LoanEase portal (sandbox)
After=network-online.target

[Service]
User=portal
WorkingDirectory=/opt/loanease
ExecStart=/opt/loanease/venv/bin/python app.py
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now loanease-portal
