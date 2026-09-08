# API Specification — TraceFall

**Phases 2-3 of this spec are implemented.** Where this document and the code disagree,
`backend/app/api/v1/` is the source of truth; the notes below record corrections made after
building against it. Endpoints for tracing, graph, patterns, attribution, risk, alerts and
reports are still design-only.

Base URL: `/api/v1` · Content type: `application/json` · Auth: `Authorization: Bearer <JWT>`
on every endpoint except `/auth/login` and `/health`.

---

## 1. Conventions

**Identifiers.** UUIDs for cases, analysis runs, and reports. Integer IDs for addresses,
transfers, and reference data.

**Timestamps.** ISO-8601 UTC with `Z` suffix, always.

**Amounts.** Every monetary value is returned as an object, never a bare number:

```json
{ "raw": "40000000000", "decimals": 6, "display": "40000.000000", "asset": "USDT",
  "chain": "TRON", "usd_approx": 40012.5 }
```

`raw` is the integer of record. `display` is a string, never a JSON number — JSON numbers are
IEEE-754 doubles and will silently corrupt large token amounts.

**Attribution.** Any object describing an address carries the tier structure verbatim:

```json
{ "tier": "PROBABLE", "entity": { "id": 12, "name": "Binance", "type": "EXCHANGE" },
  "confidence": 0.87, "method": "DEPOSIT_HEURISTIC",
  "evidence": [
    { "signal": "sweep_consistency", "value": 0.96,
      "detail": "31 of 32 inbound receipts swept to TQn9...FFbc within 12 minutes" },
    { "signal": "counterparty_diversity", "value": 32,
      "detail": "received from 32 distinct addresses with no prior relationship" }
  ],
  "disclaimer": "Probabilistic attribution. Not confirmation that this address is controlled by the named entity." }
```

`UNATTRIBUTED` returns `entity: null`, `confidence: null`, and an `explanation` field. There is
no API shape in which a `PROBABLE` claim can be mistaken for a `CONFIRMED` one.

**Pagination.** Cursor-based: `?limit=50&cursor=<opaque>`; responses carry
`{ "items": [...], "next_cursor": "...", "has_more": true }`.

**Errors.** Uniform envelope, always:

```json
{ "error": { "code": "INVALID_ADDRESS", "message": "Address failed TRON base58check validation",
  "field": "address", "request_id": "7f3a..." } }
```

Codes: `UNAUTHENTICATED` 401 · `FORBIDDEN` 403 · `NOT_FOUND` 404 · `VALIDATION_ERROR` 422 ·
`INVALID_ADDRESS` 422 · `UNSUPPORTED_CHAIN` 422 · `RATE_LIMITED` 429 · `PROVIDER_UNAVAILABLE`
503 · `ANALYSIS_IN_PROGRESS` 409 · `INTERNAL_ERROR` 500. Internal errors return the
`request_id` and nothing else.

**Rate limiting.** Per user. `429` carries `Retry-After`. Analysis creation is limited more
tightly than reads.

**As built:** only login is throttled so far (5 attempts per account per 15 minutes), and it
returns `401` with an explanatory message rather than `429`. General per-user rate limiting
lands in Phase 12.

---

## 2. Auth

### `POST /auth/login`
No auth. → `200 { access_token, refresh_token, token_type, expires_in, user }`.
`401 UNAUTHENTICATED` on bad credentials — deliberately identical response for unknown user and
wrong password.

**Also sets the refresh cookie** (below). The refresh token is returned *both* in the body and
as the cookie: the cookie is additive, so non-browser clients are unaffected.

### `POST /auth/refresh` → a full `TokenResponse`.
**As built:** the refresh token is *rotated*, not just exchanged — the presented token is
revoked and a new one issued, so replaying it fails. The response carries both tokens and the
user, identical in shape to login, and re-sets the refresh cookie with the rotated token.

The token is read from the `tracefall_refresh` cookie when one is present, and from the request
body (`{ "refresh_token": "…" }`) otherwise. Cookie-first means a browser converges on the newest
token even if its in-memory copy has fallen behind; the body fallback keeps existing API clients
working unchanged. With neither, `401 UNAUTHENTICATED`.

**This is the session-recovery endpoint.** A browser holds tokens in memory only (SECURITY.md §9),
so a page reload loses them — but not the httpOnly cookie. `POST /auth/refresh` **with an empty
body** therefore restores a full session: a working access token, a rotated refresh token, and the
user. No separate `GET /auth/session` exists; a bare refresh is that endpoint.

### `POST /auth/logout` → revokes **every** refresh token for the user, and clears the refresh
cookie (same name, path and flags, `Max-Age=0`). Server-side revocation is what ends the session;
clearing the cookie stops the browser replaying a token it can no longer use.

### `GET /auth/me` → current user and role.

### The refresh cookie

| | |
|---|---|
| **Name** | `tracefall_refresh` |
| **Value** | the current refresh token |
| **`HttpOnly`** | always — script cannot read it, so an XSS cannot exfiltrate the session |
| **`SameSite=Lax`** | a cross-site `POST` does not carry it, which is the CSRF defence for `/auth/refresh` and `/auth/logout` |
| **`Path=/api/v1/auth`** | the only routes that need it; it never rides along on case or analysis requests |
| **`Max-Age`** | `REFRESH_TOKEN_DAYS` (default 7 days), matching the token's own expiry |
| **`Secure`** | **set when `ENVIRONMENT=production`, unset in development** |

`Secure` is environment-driven rather than hardcoded because it cuts both ways: a `Secure` cookie
is silently dropped by the browser over plain HTTP, which would break local development on
`http://localhost`, while omitting it in production would let the token ride a downgraded request.
It is read from settings, so a production deployment cannot accidentally ship the development
behaviour.

---

## 3. Cases

### `POST /cases` — create a case (FR-01)
**Auth:** `INVESTIGATOR`+

```json
{ "title": "USDT investment fraud — complainant Rohtak",
  "ncrp_reference": "NCRP2026030112345", "fir_reference": "FIR/2026/0142",
  "description": "Victim transferred USDT after a Telegram trading-group solicitation.",
  "reported_loss_inr": 4500000, "incident_date": "2026-08-14", "priority": "HIGH" }
```
→ `201` with the created case. `422` on validation failure.

### `GET /cases` — list
Query: `status`, `priority`, `q`, `limit`, `cursor`. → `200` paginated. Returns only cases the
caller owns or is assigned to (NFR-08); `ADMIN` and `ANALYST` see all.

**As built:** `q` matches case number, NCRP reference, FIR reference and title. It does **not**
search address strings — that needs a join through `case_addresses` and is worth adding.
`risk_band` and `owner` filters are not implemented (risk scores do not exist yet). Any
authenticated role including `VIEWER` may list cases.

### `GET /cases/{case_id}` — detail
→ `200` with the case record. `404` if not found *or* not permitted — the API does not
distinguish these, to avoid leaking case existence.

**As built:** returns a bare case object. Addresses, analysis runs and the timeline are separate
calls (`/addresses`, `/analyses`, `/timeline`). Risk summary and alert count do not exist yet.
Composing them server-side is worth doing once the underlying data exists, to save the client
four round trips.

### `PATCH /cases/{case_id}` — update status, priority, title, description.
### `POST /cases/{case_id}/notes` — add a note, optionally pinning a finding (FR-06).
### `GET /cases/{case_id}/timeline` — the human-readable activity log (FR-05).
### `GET /cases/{case_id}/correlations` — addresses this case shares with others

```json
{ "shared_addresses": [
    { "address": "TLFq…", "chain": "TRON", "case_count": 2,
      "combined_reported_loss_inr": "450000",
      "cases": [ { "case_id": "…", "case_number": "TF-2026-0002",
                   "title": "…", "reported_loss_inr": "250000" } ] } ],
  "note": "A shared address is an on-chain fact, not a conclusion…" }
```

Most-shared first. **Confirmed exchange, mixer, bridge and merchant addresses are excluded** —
a hot wallet appears in nearly every trace, so including it would bury the addresses that
actually link cases. Only cases the caller can already open are reachable, through the same
visibility policy as `GET /cases`: an investigator sees links across their own cases, an
analyst or admin across the department.

---

## 4. Suspect addresses

### `POST /cases/{case_id}/addresses` — add a suspect address (FR-02, FR-10..14)

```json
{ "address": "TXn8kL2mQpR4vY7wZ3aB6cD9eF1gH5jK2m",
  "chain": "TRON",
  "role": "SUSPECT",
  "reported_amount": { "value": "40000", "asset_symbol": "USDT" },
  "reported_at": "2026-08-14T09:32:00Z",
  "notes": "Address supplied by complainant from Telegram chat" }
```

`chain` is optional — omitted, it is auto-detected from format; if ambiguous the response is
`422 UNSUPPORTED_CHAIN` listing the candidates so the client can ask.

→ `201`:
```json
{ "id": 8812, "address": "TXn8kL2mQpR4vY7wZ3aB6cD9eF1gH5jK2m",
  "display_address": "TXn8kL2mQpR4vY7wZ3aB6cD9eF1gH5jK2m", "chain": "TRON",
  "is_contract": false, "role": "SUSPECT",
  "reported_amount": "40000", "reported_asset_symbol": "USDT",
  "reported_at": "2026-08-14T09:32:00Z", "added_at": "2026-09-05T12:00:00Z",
  "cross_case_matches": [ { "case_id": "…", "case_number": "TF-2026-0091", "owner_id": 4 } ] }
```

`display_address` is the form to show the user — for Ethereum that is the EIP-55 checksummed
casing, while `address` is the lowercase canonical form used for lookups.

`reported_amount` and `reported_asset_symbol` echo what the victim reported, stored as given.
They are converted to raw integer units only once the asset is known, because a token's decimals
must never be guessed.

`cross_case_matches` implements FR-07 and fires at intake, not later — an investigator should
learn immediately that another officer is working the same address.

**Errors.** `422 INVALID_ADDRESS` with the specific failure (bad checksum, wrong length,
unsupported format). Validation happens before any network call (FR-12).

### `DELETE /cases/{case_id}/addresses/{id}` — remove a suspect address (audited).

---

## 5. Analysis

### `POST /cases/{case_id}/analyses` — start analysis (FR-120)
**Auth:** `INVESTIGATOR`+ · Rate limited.

```json
{ "address_id": 8812, "direction": "FORWARD", "max_depth": 5,
  "taint_threshold": 0.01, "time_window_days": 180,
  "stop_at_services": true, "include_patterns": true, "include_risk": true }
```

All parameters optional; defaults from config. → `202`:

```json
{ "analysis_run_id": "3f2b…", "status": "QUEUED",
  "poll_url": "/api/v1/analyses/3f2b…", "estimated_seconds": 75 }
```

`409 ANALYSIS_IN_PROGRESS` if a run for this address is already active.

### `GET /analyses/{run_id}` — status and progress (FR-121)

**As built:** the response carries `root_address_id` and `root_address` so a progress screen can
name the address being analysed. The `stages` array is currently **always empty** — per-stage
timings are not persisted yet, so a client must derive the stage list from `status` and `stage`.
Persisting per-stage rows is worth doing when the real stages land.

```json
{ "id": "3f2b…", "case_id": "…", "status": "RUNNING",
  "stage": "TRACING", "progress_pct": 55,
  "stages": [
    { "name": "RETRIEVAL",    "status": "COMPLETED", "duration_ms": 8420, "detail": "412 transfers from 2 providers" },
    { "name": "NORMALIZATION","status": "COMPLETED", "duration_ms": 190 },
    { "name": "ENRICHMENT",   "status": "COMPLETED", "duration_ms": 640 },
    { "name": "TRACING",      "status": "RUNNING",   "detail": "depth 3 of 5, 214 nodes" },
    { "name": "GRAPH",        "status": "PENDING" },
    { "name": "PATTERNS",     "status": "PENDING" },
    { "name": "ATTRIBUTION",  "status": "PENDING" },
    { "name": "RISK",         "status": "PENDING" }
  ],
  "degradations": [], "partial_results_available": true }
```

`status` `PARTIAL` means the run completed with one or more degradable stages skipped;
`degradations` then lists `{ stage, reason }`. This is a success state, not a failure.

### `POST /analyses/{run_id}/cancel` → `202` (FR-123).
### `GET /cases/{case_id}/analyses` — list runs for a case, newest first (FR-124).

---

## 6. Results

### `GET /analyses/{run_id}/transactions` — normalized transfers
Query: `address`, `asset`, `direction`, `from`, `to`, `min_amount`, `status`, `limit`,
`cursor`. → paginated `Transfer` objects, each with `explorer_url` for one-click verification
against a public block explorer — an investigator must always be able to check our work.

### `GET /analyses/{run_id}/trace` — the raw trace (FR-40..48)

```json
{ "root": { "address": "TXn8…", "chain": "TRON" },
  "anchor_tx_hash": "a91f…", "direction": "FORWARD",
  "params": { "max_depth": 5, "taint_threshold": 0.01, "taint_model": "HAIRCUT" },
  "taint_model_note": "Proportional (haircut) attribution. Amounts shown are attributed value, not identifiable coins.",
  "node_count": 214, "edge_count": 389,
  "terminals": [
    { "address": "TQn9…", "depth": 3, "taint_share": 0.62,
      "tainted_amount": { "raw": "24800000000", "decimals": 6, "display": "24800.000000", "asset": "USDT" },
      "termination_reason": "SERVICE_BOUNDARY",
      "attribution": { "tier": "CONFIRMED", "entity": { "name": "Binance", "type": "EXCHANGE" },
                       "source": { "name": "…", "dataset_date": "2026-07-01" } } }
  ],
  "top_paths": [ { "path": ["TXn8…","TAb3…","TQn9…"], "attributed_value": {…}, "hops": 2 } ] }
```

### `GET /analyses/{run_id}/graph` — render-ready graph (FR-90..96)
Query: `max_nodes` (default 500), `min_taint`, `expand_node`.

```json
{ "nodes": [ { "id": "TXn8…", "chain": "TRON", "depth": 0, "taint_share": 1.0,
               "entity_type": "UNKNOWN", "attribution_tier": "UNATTRIBUTED",
               "risk_band": "CRITICAL", "risk_score": 84,
               "balance": {…}, "first_seen": "…", "last_seen": "…",
               "in_degree": 47, "out_degree": 12, "is_terminal": false, "is_root": true } ],
  "edges": [ { "source": "TXn8…", "target": "TAb3…", "asset": "USDT",
               "total_value": {…}, "tainted_value": {…}, "transfer_count": 3,
               "first_at": "…", "last_at": "…", "tx_hashes": ["a91f…"] } ],
  "truncated": true, "total_nodes": 214, "returned_nodes": 500,
  "measures": { "chokepoints": [ { "address": "TAb3…", "betweenness": 0.41 } ],
                "components": 1 } }
```

`truncated` is always present. The UI must show it — silently hiding half a fund flow from an
investigator is unacceptable.

### `GET /addresses/{chain}/{address}/intelligence` — wallet intelligence
Not scoped to a run; this is what is known about the address.

```json
{ "address": "TQn9…", "chain": "TRON", "is_contract": false,
  "profile": { "first_seen": "2024-11-02T…", "age_days": 672,
    "tx_count_in": 18402, "tx_count_out": 12,
    "unique_counterparties_in": 15330, "unique_counterparties_out": 2,
    "total_in": {…}, "total_out": {…}, "balance": {…},
    "median_dwell_seconds": 430, "sweep_ratio": 0.98 },
  "labels": [ { "source": "…", "label": "Binance hot wallet", "dataset_date": "2026-07-01",
                "reliability": "HIGH" } ],
  "attribution": { "tier": "CONFIRMED", … },
  "data_completeness": { "complete": false, "reason": "PAGE_LIMIT",
                         "note": "High-volume address; first 10000 transfers retrieved" } }
```

`data_completeness` is mandatory on this response. An investigator reasoning about a partial
picture must know it is partial.

### `GET /analyses/{run_id}/attributions` — all attributions in the run (FR-70..77)
Query: `tier`, `entity_type`. → array of attribution objects as in §1.

### `GET /analyses/{run_id}/risk` — risk assessments (FR-80..86)

```json
{ "root": {
    "address": "TXn8…", "score": 84, "band": "CRITICAL", "confidence": 0.78,
    "config_version": "risk-weights-v1.2", "engine_version": "1.0.0",
    "signals": [
      { "name": "mixer_interaction", "raw_value": true, "weight": 25, "points": 25,
        "description": "Tainted value reached a known mixer at depth 2" },
      { "name": "fan_out_degree", "raw_value": 47, "weight": 15, "points": 12,
        "description": "Distributed to 47 addresses within 6 minutes" },
      { "name": "median_dwell_seconds", "raw_value": 95, "weight": 10, "points": 9,
        "description": "Funds held for a median of 95 seconds before onward transfer" }
    ],
    "not_evaluated": [ { "name": "wallet_age_signal", "reason": "First-seen block unavailable from provider" } ],
    "disclaimer": "Investigative prioritisation score. Not a probability of fraud and not evidence of criminal conduct."
  },
  "nodes": [ … ] }
```

`not_evaluated` exists so a missing signal is visible rather than indistinguishable from a
zero-scoring one (FR-83).

### `GET /analyses/{run_id}/patterns` — detected patterns (FR-60..66)
Each finding carries `pattern_type`, `severity`, `subject_address`, `involved_addresses`,
`trigger_tx_hashes`, `metrics`, `explanation`, and a required `false_positive_note`.

---

## 7. Alerts

### `GET /alerts` — global alert feed. Query: `severity`, `type`, `acknowledged`, `case_id`.
### `GET /cases/{case_id}/alerts` — case-scoped.
### `POST /alerts/{id}/acknowledge` — body `{ "note": "…" }` → audited (FR-102).

---

## 8. Reports

### `POST /cases/{case_id}/reports` — generate (FR-110..116)

```json
{ "analysis_run_id": "3f2b…", "format": "PDF", "report_type": "FULL",
  "include_graph_image": true, "include_evidence_appendix": true,
  "narrative": "TEMPLATE" }
```

`narrative` is `TEMPLATE` or `LLM`; `LLM` silently degrades to `TEMPLATE` if unavailable, and
the response says which was used. → `202 { report_id, status, poll_url }`.

### `GET /reports/{report_id}` → metadata including `content_sha256` and `narrative_source`.
### `GET /reports/{report_id}/download` → the file, `Content-Disposition: attachment`. Audited.
### `GET /cases/{case_id}/reports` → list.
### `GET /analyses/{run_id}/freeze-request` — the draft KYC and freeze request

```json
{ "recipient_name": "Binance", "recipient_address": "TWBA…",
  "tier": "PROBABLE", "confidence": 0.82, "text": "DRAFT — for review…" }
```

Plain text, generated on read: it is a draft an investigator edits and sends on their own
letterhead, not a record of what was sent, so nothing is stored or hashed. The tier is carried
as its own field and is never folded into `recipient_name`. A `PROBABLE` attribution produces a
letter that says so and asks the recipient to confirm the address is theirs; an unattributed
one is still addressed to the operator of the receiving address, because exchanges do not
publish customer deposit addresses and a VASP recognises its own regardless.

---

## 9. Reference and integration

### `GET /chains` → supported chains and their status.
### `GET /entities` → known entities. Query: `type`, `q`.
### `GET /health` → `{ status, version, live_mode, queue_reachable, providers[] }`.
No auth; no internal detail beyond provider reachability.

**As built:** `providers` is empty in fixture mode (nothing is contacted, so an empty list is the
honest answer) and otherwise reports `{name, reachable, last_check, detail}` derived from the
outcome of real requests rather than from a probe — `/health` is the container healthcheck and
must not make network calls. `reachable: null` means "not used since the last restart", which is
different from "down".

### `POST /integration/submit` — integration-ready intake (FR-130)
**Auth:** API key, `ANALYST` scope. Demonstrates how an external system such as NCRP *could*
submit an address. **This is a capability demonstration, not a live government integration** —
see [LIMITATIONS.md](LIMITATIONS.md).

```json
{ "external_reference": "NCRP2026030112345", "address": "TXn8…", "chain": "TRON",
  "reported_amount": { "value": "40000", "asset_symbol": "USDT" },
  "reported_at": "2026-08-14T09:32:00Z", "callback_url": "https://…" }
```
→ `202 { case_id, analysis_run_id, status_url }`.

---

## 10. Endpoint index

| Method | Path | Purpose | Auth | Req |
|---|---|---|---|---|
| POST | `/auth/login` | Authenticate | — | NFR-08 |
| POST | `/cases` | Create case | INV+ | FR-01 |
| GET | `/cases` | List cases | any role | FR-03 |
| GET | `/cases/{id}` | Case detail | INV+ | FR-03 |
| PATCH | `/cases/{id}` | Update case | INV+ | FR-04 |
| POST | `/cases/{id}/notes` | Add note / pin finding | INV+ | FR-06 |
| GET | `/cases/{id}/timeline` | Activity timeline | INV+ | FR-05 |
| POST | `/cases/{id}/addresses` | Add suspect address | INV+ | FR-02, FR-07, FR-10 |
| GET | `/cases/{id}/addresses` | List case addresses | any role | FR-02 |
| DELETE | `/cases/{id}/addresses/{aid}` | Remove suspect address | INV+ | FR-02 |
| DELETE | `/cases/{id}` | Delete a case | ADMIN | — |
| POST | `/cases/{id}/analyses` | Start analysis | INV+ | FR-120 |
| GET | `/analyses/{id}` | Status + progress | INV+ | FR-121 |
| POST | `/analyses/{id}/cancel` | Cancel | INV+ | FR-123 |
| GET | `/analyses/{id}/transactions` | Normalized transfers | INV+ | FR-30 |
| GET | `/analyses/{id}/trace` | Trace result | INV+ | FR-40 |
| GET | `/analyses/{id}/graph` | Render-ready graph | INV+ | FR-90 |
| GET | `/analyses/{id}/patterns` | Pattern findings | INV+ | FR-60 |
| GET | `/analyses/{id}/attributions` | VASP attributions | INV+ | FR-70 |
| GET | `/analyses/{id}/risk` | Risk assessments | INV+ | FR-80 |
| GET | `/addresses/{chain}/{addr}/intelligence` | Wallet intelligence | INV+ | FR-70, FR-27 |
| GET | `/alerts` | Alert feed | INV+ | FR-101 |
| POST | `/alerts/{id}/acknowledge` | Acknowledge | INV+ | FR-102 |
| POST | `/cases/{id}/reports` | Generate report | INV+ | FR-110 |
| GET | `/reports/{id}/download` | Download report | INV+ | FR-110 |
| POST | `/integration/submit` | External intake | API key | FR-130 |
| GET | `/health` | Health | — | — |
