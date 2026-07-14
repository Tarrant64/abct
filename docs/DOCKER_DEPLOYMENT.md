# Docker Deployment Guide

ABCT ships as a single Docker image built from [`abct-docker/Dockerfile`](../abct-docker/Dockerfile). This guide covers the two supported deployment patterns and platform-specific notes for common Docker hosts.

## What the container provides

- **Web dashboard** served on container port **80** (443 available for TLS via the bundled nginx config)
- **Health endpoint** at `/health` (used by the built-in Docker healthcheck)
- **Persistent data** (SQLite database, caches) under `/app/data` — always mount a volume here
- **Configuration** entirely via environment variables — see [`abct-docker/.env.example`](../abct-docker/.env.example) for the full list. Only `BLOCKFROST_API_KEY` is required for Cardano tracking; everything else is optional.

## Pattern 1: docker-compose (dedicated container IP)

The shipped [`abct-docker/docker-compose.yml`](../abct-docker/docker-compose.yml) attaches the container to an **external Docker network** and can give it its own IP address on your LAN. This suits homelab hosts (Unraid, bare Linux) where the dashboard should be reachable at `http://<container-ip>/` without port juggling.

```bash
git clone https://github.com/Tarrant64/abct.git
cd abct/abct-docker
cp .env.example .env
nano .env                      # add API keys

# The compose file expects an existing Docker network.
# Set these in .env or your shell:
#   ABCT_DOCKER_NETWORK  - name of the external network (e.g. a macvlan/ipvlan network)
#   ABCT_STATIC_IP       - optional fixed IP for the container on that network

docker compose up -d
```

Access the dashboard at `http://<ABCT_STATIC_IP>/` (port 80).

## Pattern 2: standard bridge network (port mapping)

For desktops, VPSes, NAS GUIs, and anywhere you don't want a dedicated container IP, run the image on the default bridge and publish a port:

```bash
git clone https://github.com/Tarrant64/abct.git
cd abct
docker build -t abct-dashboard -f abct-docker/Dockerfile .

docker run -d \
  --name abct-dashboard \
  --restart unless-stopped \
  -p 8080:80 \
  -v abct-data:/app/data \
  --env-file abct-docker/.env \
  abct-dashboard
```

Access the dashboard at `http://localhost:8080`.

## Platform notes

### Unraid

Two options:

1. **Community template**: [`abct-docker/unraid/abct-dashboard.xml`](../abct-docker/unraid/abct-dashboard.xml) — add it as a template and fill in the paths/keys in the Unraid UI.
2. **Deploy from Git**: [`abct-docker/deploy_from_git.sh`](../abct-docker/deploy_from_git.sh) clones the repo, builds the image, and replaces the running container in one step. Configure it with environment variables (see the header of the script): `ABCT_DATA_PATH`, `ABCT_DOCKER_NETWORK`, `ABCT_STATIC_IP` (optional), `ABCT_ENV_FILE`, `GIT_REPO`, `GIT_BRANCH`.

### TrueNAS SCALE

Use **Apps → Custom App** (or the Docker Compose app) with the Pattern 2 settings: image built from this repo or a registry you push it to, port 8080 → 80, host-path or dataset mounted at `/app/data`, environment variables from `.env.example`.

### Synology

In **Container Manager**, create the container from the built image, map a NAS folder to `/app/data`, publish local port 8080 → container port 80, and add environment variables in the container settings. Synology's reverse proxy (Control Panel → Login Portal → Advanced) works well in front of it for HTTPS.

### Portainer

Create a **Stack** and paste `abct-docker/docker-compose.yml`, or add a `ports: ["8080:80"]` mapping and drop the external-network block if you prefer Pattern 2. Set the environment variables in the stack editor.

## Updating

Rebuild from the latest source and replace the container:

```bash
cd abct && git pull
docker build -t abct-dashboard -f abct-docker/Dockerfile .
docker stop abct-dashboard && docker rm abct-dashboard
# re-run your `docker run` / `docker compose up -d` command
```

On Unraid, `abct-docker/deploy_from_git.sh` performs exactly this cycle.

Your data survives updates as long as the `/app/data` volume is reused. See the [Backup & Restore guide](BACKUP_RESTORE_GUIDE.md) for exporting configuration.

## Security checklist

- **Change the default admin password** immediately (see the [Password Reset Guide](guides/PASSWORD_RESET_GUIDE.md)).
- Keep `ABCT_REQUIRE_AUTH=true` (the default).
- Do **not** port-forward the dashboard directly to the internet. Prefer a VPN (Tailscale/WireGuard), the built-in Cloudflare Tunnel support, or an authenticated reverse proxy.
- Keep your `.env` outside the repo checkout and out of any image layers.

More in [SECURITY.md](../SECURITY.md).
