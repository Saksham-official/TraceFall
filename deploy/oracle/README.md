# Zero-cost public deployment on Oracle Cloud Always Free

This is the recommended free deployment for TraceFall. It runs the existing five-container
Compose topology on one persistent VM:

```text
Vercel SPA → Caddy HTTPS → nginx → FastAPI → PostgreSQL
                                      └────→ Redis → worker
                                      └────→ persistent /data evidence and reports
```

Oracle's Always Free resources include Ampere A1 compute equivalent to 2 OCPUs and 12 GB of
memory, plus free storage quotas. Availability is subject to capacity in the selected home
region. This is a single-VM deployment: it is suitable for an SIH prototype, but it is not
high availability. Keep backups of the VM volume/database.

## 1. Create the VM

1. Create an Oracle Cloud Free Tier account. A payment method may be requested for identity
   verification; do not select a paid shape or enable paid autoscaling.
2. Create an Ubuntu 24.04 ARM VM using `VM.Standard.A1.Flex`.
3. Set shape limits to `2 OCPU` and `12 GB RAM` or less.
4. Create a boot volume of 50 GB or less.
5. Reserve a public IPv4 address.
6. Add ingress rules for TCP ports `22`, `80`, and `443` only.

If A1 capacity is unavailable, try another availability domain in the same home region. Do
not upgrade the tenancy just to bypass an Always Free capacity error.

## 2. Install Docker and Caddy

SSH to the VM:

```bash
ssh ubuntu@YOUR_PUBLIC_IP
sudo apt-get update
sudo apt-get install -y ca-certificates curl git caddy
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker
```

## 3. Put the repository on the VM

```bash
git clone https://github.com/rkhooda/TraceFall.git
cd TraceFall
```

Use the checked-in deployment commit and confirm the working tree is clean:

```bash
git log -1 --oneline
git status --short
```

## 4. Create production configuration

```bash
cp .env.example .env
openssl rand -hex 64
```

Edit `.env` and set every value below. Keep `.env` only on the VM; never commit it.

```dotenv
ENVIRONMENT=production
SECRET_KEY=PASTE_THE_RANDOM_VALUE_HERE

DATABASE_URL=postgresql+asyncpg://tracefall:STRONG_DB_PASSWORD@postgres:5432/tracefall
REDIS_URL=redis://redis:6379/0

LIVE_MODE=true
TRONGRID_BASE_URL=https://api.trongrid.io
TRONGRID_API_KEY=YOUR_TRONGRID_KEY
ETHERSCAN_BASE_URL=https://api.etherscan.io/api
ETHERSCAN_API_KEY=YOUR_ETHERSCAN_KEY
BLOCKSCOUT_BASE_URL=https://eth.blockscout.com

RATE_LIMIT_ENABLED=true
TRUST_PROXY_HEADERS=false
REFRESH_COOKIE_SAMESITE=none

EVIDENCE_STORAGE_PATH=/data/evidence
REPORT_STORAGE_PATH=/data/reports
RISK_CONFIG_PATH=config/risk_weights.yaml
LABEL_DATA_PATH=data/labels

CORS_ORIGINS=https://YOUR_VERCEL_DOMAIN
```

Set `POSTGRES_PASSWORD` in `.env` to the same strong database password. Leave
`LIVE_MODE=true`; an API failure must be surfaced as a real provider degradation, never
replaced by fixture data.

## 5. Start, migrate, and load labels

The Compose file uses named Docker volumes, so PostgreSQL, Redis, evidence, and reports are
not lost when containers restart.

```bash
docker compose -f docker-compose.yml -f docker-compose.oracle.yml up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli load-labels
docker compose ps
```

Create an administrator interactively:

```bash
docker compose exec api python -m app.cli create-admin \
  --email investigator@tracefall.gov \
  --full-name "TraceFall Investigator"
```

## 6. Enable HTTPS

Choose a hostname. A custom domain is best. If none is available, use
`YOUR_PUBLIC_IP.sslip.io`, which resolves to the VM's IP.

```bash
sudo sed -i 's/YOUR_BACKEND_HOSTNAME/YOUR_PUBLIC_IP.sslip.io/' deploy/oracle/Caddyfile
sudo cp deploy/oracle/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy obtains and renews the HTTPS certificate automatically. Confirm:

```bash
curl -fsS https://YOUR_PUBLIC_IP.sslip.io/api/v1/health
```

## 7. Configure Vercel

In the Vercel project, set the root directory to `frontend` and add this Production
environment variable:

```text
VITE_API_URL=https://YOUR_PUBLIC_IP.sslip.io
```

Redeploy the frontend. The repository client appends `/api/v1` itself.

Update `CORS_ORIGINS` in `.env` with the exact Vercel origin, restart the API, and confirm:

```bash
docker compose restart api
```

## 8. Public verification

From an incognito browser:

1. Open the Vercel URL.
2. Sign in.
3. Create a case with a valid TRON address.
4. Start an investigation.
5. Confirm the UI says `Live mode`.
6. Wait for the worker to complete the analysis.
7. Open graph, patterns, attribution, risk, and evidence.
8. Generate and download PDF, JSON, and CSV reports.
9. Refresh, sign out, sign back in, and confirm history and reports remain.

Check the VM logs while it runs:

```bash
docker compose logs --tail=200 api worker
```

## Operational limits

This deployment is free only while it stays within Oracle Always Free quotas and the public
provider limits. It is not redundant: VM loss can lose local evidence/reports unless the
Docker volume is backed up. PostgreSQL data, reports, and evidence all live on the VM's
persistent volume in this design.

The public URL is designed to remain reachable after inactivity because the VM is persistent,
not a sleep-based free web service. Oracle may still perform maintenance, and an unavailable
Always Free shape can block creation or recovery in a region.
