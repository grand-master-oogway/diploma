# vm

The Dagster VM (Debian 12, shielded VM, OS Login, no external IP). It runs as a given service account and is reached only through
IAP tunnels. The startup script installs `uv`, a Python 3.14 environment and the `firms-ua` command; Dagster and its metadata database are added in a later step.
