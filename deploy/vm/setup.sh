#!/bin/bash
# Install a built wheel on the Dagster VM and (re)configure Dagster. Run by the deploy workflow as root; safe to repeat.
#
#   sudo bash setup.sh <wheel> <storage_root> <gcp_project> <map_key_secret>
#
# Needs the base set up by the VM startup script (uv, /opt/firms-ua/venv, /usr/local/sbin/firms-ua-install).
# Writes:
#   /etc/firms-ua/env              pipeline settings for the Dagster services (identifiers only; the MAP_KEY stays in Secret Manager)
#   /var/lib/firms-ua/dagster      DAGSTER_HOME: dagster.yaml and the SQLite metadata (runs, events, schedule state)
#   dagster-webserver / dagster-daemon   systemd services; the UI listens on 127.0.0.1:3000 only (reach it through an IAP tunnel)
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: setup.sh <wheel> <storage_root> <gcp_project> <map_key_secret>" >&2
  exit 2
fi
wheel=$1 storage_root=$2 gcp_project=$3 map_key_secret=$4
venv=/opt/firms-ua/venv
dagster_home=/var/lib/firms-ua/dagster
module=firms_ua.orchestration.definitions

if [ ! -x /usr/local/sbin/firms-ua-install ]; then
  echo "the VM startup script has not run yet (no firms-ua-install)" >&2
  exit 1
fi
/usr/local/sbin/firms-ua-install "$wheel"

install -d -m 755 /etc/firms-ua
cat >/etc/firms-ua/env <<ENV
FIRMS_STORAGE_ROOT=$storage_root
FIRMS_GCP_PROJECT=$gcp_project
FIRMS_MAP_KEY_SECRET=$map_key_secret
ENV
chmod 644 /etc/firms-ua/env

if ! id firms-ua >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/firms-ua --shell /usr/sbin/nologin firms-ua
fi
install -d -o firms-ua -g firms-ua -m 750 /var/lib/firms-ua "$dagster_home"
cat >"$dagster_home/dagster.yaml" <<'YAML'
# Metadata (runs, event logs, schedule state) uses the default SQLite storage in this folder.
telemetry:
  enabled: false
concurrency:
  runs:
    max_concurrent_runs: 2
  pools:
    # Every pool without its own limit, including `firms_api` (the FIRMS ingestion asset), runs one step at a time,
    # so a single process spends the MAP_KEY budget and its client-side throttle stays accurate.
    default_limit: 1
YAML
chown firms-ua:firms-ua "$dagster_home/dagster.yaml"

write_unit() {
  local name=$1 description=$2 exec_start=$3
  cat >"/etc/systemd/system/$name.service" <<UNIT
[Unit]
Description=$description
After=network-online.target
Wants=network-online.target

[Service]
User=firms-ua
Environment=DAGSTER_HOME=$dagster_home
EnvironmentFile=/etc/firms-ua/env
WorkingDirectory=$dagster_home
ExecStart=$exec_start
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
}
write_unit dagster-webserver "Dagster UI (firms-ua)" "$venv/bin/dagster-webserver --host 127.0.0.1 --port 3000 -m $module"
write_unit dagster-daemon "Dagster daemon: schedules, run queue, backfills (firms-ua)" "$venv/bin/dagster-daemon run -m $module"

systemctl daemon-reload
systemctl enable dagster-webserver dagster-daemon
# Load the new code. Runs in progress are interrupted; launch them again (days already fetched are skipped).
systemctl restart dagster-webserver dagster-daemon
sleep 5
systemctl is-active --quiet dagster-webserver dagster-daemon || {
  journalctl -u dagster-webserver -u dagster-daemon -n 50 --no-pager >&2
  exit 1
}
echo "installed $(basename "$wheel"); dagster-webserver and dagster-daemon are running"
