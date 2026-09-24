#!/bin/bash
set -euxo pipefail
exec > >(tee -a /var/log/loanease-bootstrap.log) 2>&1
export DEBIAN_FRONTEND=noninteractive

# The private subnet reaches the internet through the NAT instance, which may still be booting.
for i in $(seq 1 30); do
  if apt-get update -y; then break; fi
  sleep 10
done
apt-get install -y postgresql

CONF=$(ls -d /etc/postgresql/*/main | head -n1)
sed -i "s/^#\?listen_addresses.*/listen_addresses = '*'/" "$CONF/postgresql.conf"
echo "host all all 10.20.0.0/16 scram-sha-256" >> "$CONF/pg_hba.conf"

# Password is generated on the box so it never lands in Terraform state or user_data.
set +x
DB_PASS=$(openssl rand -hex 16)
sudo -u postgres psql -c "CREATE USER loanease WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -c "CREATE DATABASE loanease OWNER loanease;"
umask 077
echo "$DB_PASS" > /root/db_password.txt
set -x

systemctl restart postgresql
