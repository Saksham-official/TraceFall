# Deployment

For a $0 public deployment that keeps the existing FastAPI, Redis worker, PostgreSQL, and
filesystem evidence topology together, follow [`deploy/oracle/README.md`](../deploy/oracle/README.md).
It uses Oracle Cloud Always Free compute with a persistent VM volume and Caddy HTTPS. The
Compose walkthrough below remains the local/development reference.

Railway is also supported by [`railway.json`](../railway.json), but Railway's current Free
plan is credit-limited rather than an always-on free tier. Its trial is temporary and trial
volumes are not a durable SIH production-storage solution; use the Railway procedure only
for a short submission window and monitor usage.

Render is supported by [`render.yaml`](../render.yaml) for deploying the Dockerized backend,
free managed PostgreSQL, and managed Key Value (Redis). Health checks are served at
`/api/health`.

For Render, sync the Blueprint so it creates `tracefall-cache` and wires `REDIS_URL` from
that service. Set the `CORS_ORIGINS` environment variable on `tracefall-api` to the exact
HTTPS origin of the deployed frontend (for example, `https://your-app.vercel.app`), then
redeploy. The production guard intentionally rejects the local `http://localhost` default,
wildcard origins, missing Redis, and non-`none` refresh-cookie SameSite settings.

**Target: `docker compose up` and the system runs (NFR-11).** Everything else is future.

**Verified 2026-09-05** on macOS/arm64, Docker 29.7.2, Compose v5.5.0. Five containers reach
`healthy`, the first-run sequence below completes, an investigation runs end to end through
nginx and produces a downloadable PDF, data survives `docker compose down && up`, and every
retrieval came from the committed fixture cache — `SELECT is_fixture, count(*) FROM
evidence_items` returned `t|4` and nothing else, so no provider was contacted.

---

## 1. Topology

```
┌──────────┐   ┌──────────┐   ┌──────────┐
│   web    │   │   api    │   │  worker  │
│  nginx + │──▶│ FastAPI  │◀──│  queue   │
│  React   │   │  :8000   │   │ consumer │
│  :80     │   └────┬─────┘   └────┬─────┘
└──────────┘        │              │
              ┌─────▼──────────────▼─────┐
              │  postgres:16   redis:7   │
              └──────────────────────────┘
                          │
                  ./data/evidence  (volume)
```

Five services. `api` and `worker` run the same image with different commands — one codebase,
two entrypoints, no duplication.

---

## 2. Services

| Service | Image | Purpose | Exposed |
|---|---|---|---|
| `web` | nginx:alpine + built SPA | Static assets, proxies `/api` | 80 |
| `api` | `tracefall-backend` | FastAPI | 8000 (internal) |
| `worker` | `tracefall-backend` | Pipeline execution | none |
| `postgres` | postgres:16-alpine | Primary store | none |
| `redis` | redis:7-alpine | Queue + cache | none |

**Only `web` is exposed.** PostgreSQL and Redis are never published to the host
([SECURITY.md §11](SECURITY.md)).

---

## 3. Configuration

Single `.env`, from a committed `.env.example` with empty values:

```bash
ENVIRONMENT=development            # development | production
SECRET_KEY=                        # required; generated at setup
DATABASE_URL=postgresql+asyncpg://tracefall:...@postgres:5432/tracefall
REDIS_URL=redis://redis:6379/0

LIVE_MODE=true                     # live provider retrieval (product default)
TRONGRID_API_KEY=
ETHERSCAN_API_KEY=
BLOCKSCOUT_BASE_URL=https://eth.blockscout.com

TRACE_MAX_DEPTH=5
TRACE_TAINT_THRESHOLD=0.01
TRACE_EDGE_BUDGET=5000
TRACE_FANOUT_CAP=20
GRAPH_NODE_CAP=500

RISK_CONFIG_PATH=config/risk_weights.yaml
ML_MODEL_PATH=models/deposit_classifier.txt   # optional
LLM_API_KEY=                                  # optional
EVIDENCE_STORAGE_PATH=/data/evidence
CORS_ORIGINS=http://localhost
```

**`LIVE_MODE=true` is the default.** Set `LIVE_MODE=false` explicitly for the deterministic
offline fixture walkthrough. Live deployments must configure the provider endpoints and any
required credentials before investigators start a run.

**`SECRET_KEY` has no default.** The app refuses to start without one. A committed default
secret key is how prototypes get compromised.

---

## 4. First-run sequence

```bash
git clone <repo> && cd TraceFall
cp .env.example .env
./scripts/generate-secret.sh >> .env      # writes SECRET_KEY
docker compose up -d
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli load-labels
docker compose exec api python -m app.cli create-admin   # interactive, prompts for password
open http://localhost
```

Seven commands, one of them interactive. **All seven were run and verified**; the order above
is the tested one.

The worker starts before the schema exists — that is expected, and it waits rather than
exiting. `docker compose logs worker` shows *"waiting for the database schema; run alembic
upgrade head"* until the migration lands, then *"worker ready"*.

**`create-admin` is interactive and mandatory.** There are no seeded credentials in any build —
not in development, not in the demo image ([SECURITY.md §2](SECURITY.md)).

`load-labels` ingests the committed curated label datasets and prints a summary of what loaded
and from which sources, so a missing dataset is loud rather than silent.

---

## 5. Demo deployment

The configuration used on presentation day:

```bash
LIVE_MODE=false
ENVIRONMENT=development
```

**Pre-flight checklist:**
1. `docker compose up -d`, wait for healthchecks green.
2. Migrations applied, labels loaded, admin created.
3. **Fixture cache present and complete for all demo addresses** —
   `python scripts/demo_fixtures.py --check` replays every demo trace offline through the
   real tracing engine and exits non-zero naming any address whose fixture is missing.
   Then **run each demo case once** and capture anything its graph still reports under
   `unavailable_addresses` — the check reads one address's own responses, while the
   pipeline reads the database, and a truncated counterparty can carry an edge the check
   never sees.
4. Full demo walkthrough executed once, end to end, on the actual presentation laptop.
5. Screen resolution checked at 1366×768; both light and dark themes verified.
6. **Network cable unplugged and the demo re-run**, to prove the offline path genuinely works.

Step 6 is the one that saves the presentation. Do not skip it.

A fallback recording of the full walkthrough is produced during Phase 15 and kept on the
presentation machine. Judges rarely need it; having it removes the fear that changes how a
person presents.

---

## 6. Healthchecks

Every service defines a healthcheck; `api` and `worker` depend on `postgres` and `redis` being
healthy, not merely started. `GET /health` reports version, provider reachability, and
`live_mode` — the last of which is deliberately visible so nobody is confused about what they
are looking at.

---

## 7. Data persistence

| Volume | Contents | Backup |
|---|---|---|
| `postgres_data` | Database | `pg_dump`, documented |
| `evidence_data` | Raw provider responses, reports, graph images | Filesystem copy |
| `redis_data` | Cache and queue | **Not backed up** — reconstructible by design |

Redis holding nothing that needs backup is a property worth preserving: it means the cache is
genuinely a cache ([DATA_ARCHITECTURE.md §7](DATA_ARCHITECTURE.md)).

---

## 8. Production notes (documented, not built)

Beyond the compose setup, a real deployment would need:

- **TLS termination** at a reverse proxy, HSTS enabled.
- **Managed PostgreSQL** with automated backups and PITR.
- **`ENVIRONMENT=production`**, which disables API docs and debug output.
- **Secrets from a secret manager**, not a `.env` file.
- **Log aggregation** for the structured JSON logs.
- **Metrics and alerting** on job failure rate, provider error rate, and queue depth.
- **Horizontal scaling:** multiple `api` replicas behind a load balancer; multiple `worker`
  replicas — the queue already supports both.

**Not needed and not planned:** Kubernetes, service mesh, multi-region. None of these address
the actual bottleneck, which is third-party API rate limits
([SYSTEM_ARCHITECTURE.md §7](SYSTEM_ARCHITECTURE.md)).

---

## 9. CI/CD

**On every PR:** lint, type check, full offline test suite, coverage gates, security scans,
Docker build.
**On merge to main:** the above plus E2E and the golden-case regression, then image publication.
**Scheduled:** live smoke tests against real APIs
([TESTING_STRATEGY.md §13](TESTING_STRATEGY.md)) — which is how we discover a provider changed
its response shape before it breaks a demo rather than during one.
