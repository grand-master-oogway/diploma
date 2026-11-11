# deploy

Files the deploy workflow (`.github/workflows/deploy.yml`) copies to the Dagster VM and runs there.

- `vm/setup.sh`: installs the built wheel (through `firms-ua-install` from the VM startup script) and configures Dagster: settings file
  `/etc/firms-ua/env`, `DAGSTER_HOME=/var/lib/firms-ua/dagster` with `dagster.yaml`, and the `dagster-webserver` / `dagster-daemon`
  systemd services, which it restarts. Idempotent; run as root.

Changing these files ships with the next deploy; no Terraform apply or VM reset is needed. See `docs/deploy.md`.
