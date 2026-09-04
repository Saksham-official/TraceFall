# Database Design — TraceFall

Logical data model. **No implementation in this phase** — no migrations, no ORM classes. This
document is the contract Phase 2 implements.

Store: **PostgreSQL 16**, single database. Rationale: ADR-003 in
[DECISIONS.md](DECISIONS.md).

---

## 1. Entity map

```
users ──owns──< cases ──has──< case_addresses >── addresses ──on──> chains
                  │                                   │
                  ├──< analysis_runs                   ├──< address_profiles
                  │       │                            ├──< attributions >── entities
                  │       ├──< traces ──< trace_nodes  └──< address_labels >── label_sources
                  │       │      │        └─< trace_edges
                  │       │      └──< pattern_findings
                  │       ├──< risk_assessments
                  │       └──< alerts
                  ├──< case_notes
                  ├──< reports
                  └──< evidence_items

transactions ──< transfers >── assets
audit_log (append-only, references everything, owned by nothing)
```

---

## 2. Reference and identity tables

### `chains`
Static reference. `id` (smallint PK), `code` (`TRON`, `ETHEREUM`), `name`, `native_asset_id`,
`explorer_url_template`, `address_format`, `is_enabled`.

Kept as a table rather than an enum so a chain can be added without a migration and so
per-chain configuration has somewhere to live.

### `assets`
`id` (PK), `chain_id` (FK), `contract_address` (NULL for native currency), `symbol`, `name`,
`decimals`, `is_native`, `is_stablecoin`, `first_seen_at`.
**Unique:** `(chain_id, contract_address)` — with a partial unique index enforcing one native
asset per chain.

Native currency is an ordinary row. This removes branching from every consumer.

### `users`
`id` (PK), `email` (unique), `password_hash`, `full_name`, `role` (`ADMIN` | `INVESTIGATOR` |
`ANALYST` | `VIEWER`), `organisation`, `is_active`, `created_at`, `last_login_at`.

Passwords hashed with Argon2id. See [SECURITY.md](SECURITY.md).

---

## 3. Case domain

### `cases`
`id` (PK, UUID), `case_number` (unique, human-readable, generated), `title`,
`ncrp_reference` (nullable), `fir_reference` (nullable), `description`,
`reported_loss_inr` (NUMERIC), `incident_date`, `status` (`OPEN` | `ANALYSING` | `REVIEW` |
`CLOSED`), `priority`, `owner_id` (FK users), `created_at`, `updated_at`, `closed_at`.

`ncrp_reference` is a free-text reference number only. **No victim PII is stored** — see
[PRIVACY_AND_COMPLIANCE.md](PRIVACY_AND_COMPLIANCE.md).

### `case_addresses`
Links a case to a suspect address, with the victim-transfer context that anchors the trace.

`id` (PK), `case_id` (FK), `address_id` (FK), `role` (`SUSPECT` | `VICTIM_SOURCE` |
`DISCOVERED`), `reported_amount_raw` (nullable), `reported_asset_id` (nullable),
`reported_at` (nullable), `anchor_tx_hash` (nullable, resolved during analysis), `notes`,
`added_by` (FK users), `added_at`.
**Unique:** `(case_id, address_id, role)`.

### `case_notes`
`id`, `case_id`, `author_id`, `body`, `pinned_finding_type` (nullable), `pinned_finding_id`
(nullable), `created_at`. Pinning is how an investigator marks a finding for the report (FR-06).

### `case_timeline`
`id`, `case_id`, `actor_id`, `event_type`, `payload` (JSONB), `created_at`. Append-only,
user-visible narrative of the case (FR-05). Distinct from `audit_log`, which is a security
artefact and includes reads.

---

## 4. Address domain

### `addresses`
`id` (PK), `chain_id` (FK), `address` (canonical form — see
[DATA_ARCHITECTURE.md §5](DATA_ARCHITECTURE.md)), `is_contract` (nullable tri-state: unknown
until checked), `first_seen_block`, `first_seen_at`, `last_seen_at`, `created_at`.
**Unique:** `(chain_id, address)`.

The same address may appear in many cases; it is stored once. This is what makes cross-case
correlation (FR-07) a simple join rather than a search.

### `address_profiles`
Derived statistics and features. Versioned by data freshness so a stale profile is never reused.

`id`, `address_id` (FK), `data_version` (latest ingested block height), `computed_at`,
`tx_count_in`, `tx_count_out`, `unique_counterparties_in`, `unique_counterparties_out`,
`total_in_raw`, `total_out_raw`, `balance_raw`, `age_days`, `active_days`,
`median_dwell_seconds`, `sweep_ratio`, `distinct_assets`, `features` (JSONB — the full
behavioural feature vector consumed by the classifier and the risk engine).
**Unique:** `(address_id, data_version)`.

Keeping the feature vector in JSONB is deliberate: features evolve during development and each
one does not deserve a migration. The named columns above are the ones queried directly.

### `entities`
The real-world things addresses may belong to.

`id` (PK), `name` (e.g. "Binance"), `entity_type` (`EXCHANGE` | `MIXER` | `BRIDGE` |
`TOKEN_CONTRACT` | `DEFI` | `GAMBLING` | `SANCTIONED` | `MERCHANT` | `UNKNOWN`), `website`,
`jurisdiction`, `is_fiu_ind_registered` (nullable tri-state), `is_sanctioned`,
`contact_channel` (how an investigator would actually reach them — the operationally useful
field), `notes`, `created_at`.

`is_fiu_ind_registered` is nullable-unknown rather than boolean, because "we don't know"
must be distinguishable from "no" (FR-77).

### `label_sources`
Provenance for every label. Without this table, `CONFIRMED` means nothing.

`id`, `name`, `url`, `licence`, `description`, `reliability` (`HIGH` | `MEDIUM` | `LOW`),
`ingested_at`, `dataset_date`, `record_count`.

### `address_labels`
`id`, `address_id` (FK), `entity_id` (FK, nullable), `label_source_id` (FK), `label_text`,
`label_type`, `confidence` (nullable — NULL means the source asserts it flatly),
`ingested_at`.
**Unique:** `(address_id, label_source_id, label_text)`.

Multiple sources may label one address differently. **Conflicts are stored, not resolved**
(FR-75); the attribution engine surfaces the disagreement to the investigator.

### `attributions`
The system's own tiered conclusion about an address, per analysis run.

`id`, `analysis_run_id` (FK), `address_id` (FK), `entity_id` (FK, nullable),
`entity_type`, `tier` (`CONFIRMED` | `PROBABLE` | `UNATTRIBUTED`), `confidence` (NULL unless
`PROBABLE`), `method` (`DATASET_MATCH` | `DEPOSIT_HEURISTIC` | `CLASSIFIER` | `MANUAL`),
`evidence` (JSONB — the enumerated evidence list, FR-72), `engine_version`, `computed_at`.

**Constraint:** `tier='CONFIRMED'` requires a non-null `address_label` reference in `evidence`;
`tier='PROBABLE'` requires non-null `confidence` and a non-empty evidence array. Enforced as a
CHECK constraint, not left to application discipline — this is the product's central integrity
rule and belongs in the database.

### `attribution_overrides`
Investigator judgement, kept strictly separate from machine output (FR-78).

`id`, `attribution_id` (FK), `address_id`, `user_id`, `override_tier`, `override_entity_id`,
`justification` (required), `created_at`. Never updates `attributions`.

---

## 5. Blockchain data domain

### `transactions`
`id` (PK), `chain_id`, `tx_hash`, `block_number`, `block_time` (timestamptz UTC),
`from_address_id`, `to_address_id` (nullable — contract creation), `fee_raw`, `status`,
`nonce`, `input_size`, `ingested_at`.
**Unique:** `(chain_id, tx_hash)`.

### `transfers`
The workhorse table. One row per value movement.

`id` (PK, bigint), `transaction_id` (FK), `chain_id`, `tx_hash` (denormalised for query
speed), `transfer_index`, `block_number`, `block_time`, `from_address_id`, `to_address_id`,
`asset_id`, `amount_raw` (NUMERIC(78,0)), `decimals`, `usd_value_approx` (nullable),
`status`, `is_internal`, `ingested_at`.
**Unique:** `(chain_id, tx_hash, transfer_index)` — the idempotency key.

`decimals` is denormalised deliberately (see DATA_ARCHITECTURE §6).

---

## 6. Analysis domain

### `analysis_runs`
`id` (PK, UUID), `case_id` (FK), `root_address_id` (FK), `params` (JSONB — depth, thresholds,
window, direction), `status` (`QUEUED` | `RUNNING` | `COMPLETED` | `PARTIAL` | `FAILED` |
`CANCELLED`), `stage` (current pipeline stage), `progress_pct`, `degradations` (JSONB — which
stages ran partially and why, FR-122), `engine_versions` (JSONB), `started_at`,
`completed_at`, `error`, `triggered_by` (FK users).

Every derived artefact hangs off an `analysis_run`. Re-running creates a new one (FR-124);
nothing is overwritten.

### `traces`
`id`, `analysis_run_id` (FK), `root_address_id`, `direction` (`FORWARD` | `BACKWARD`),
`anchor_tx_hash` (nullable), `max_depth`, `taint_threshold`, `edge_budget`,
`taint_model` (`HAIRCUT` — recorded so a future FIFO option remains explicable),
`node_count`, `edge_count`, `total_traced_raw`, `computed_at`.

### `trace_nodes`
`id`, `trace_id` (FK), `address_id` (FK), `depth`, `taint_share` (NUMERIC — fraction of the
original tainted value attributed here), `tainted_amount_raw`, `is_terminal`,
`termination_reason` (`MAX_DEPTH` | `BELOW_THRESHOLD` | `SERVICE_BOUNDARY` | `NO_OUTFLOW` |
`EDGE_BUDGET` | `TIME_WINDOW`, NULL if not terminal), `first_reached_at`.
**Unique:** `(trace_id, address_id)`.

### `trace_edges`
`id`, `trace_id` (FK), `from_address_id`, `to_address_id`, `asset_id`, `total_amount_raw`,
`tainted_amount_raw`, `transfer_count`, `first_transfer_at`, `last_transfer_at`,
`tx_hashes` (JSONB array — the drill-down path back to L1).
**Unique:** `(trace_id, from_address_id, to_address_id, asset_id)`.

Edges are *aggregated* flows between an address pair, not individual transfers. Individual
transfers remain reachable via `tx_hashes`. This is what keeps the graph renderable.

### `pattern_findings`
`id`, `analysis_run_id` (FK), `pattern_type` (`FAN_OUT` | `FAN_IN` | `RAPID_TRANSFER` |
`PEEL_CHAIN` | `DORMANCY_BURST` | `STRUCTURING`), `severity` (`LOW`|`MEDIUM`|`HIGH`),
`subject_address_id`, `involved_address_ids` (JSONB), `trigger_tx_hashes` (JSONB),
`metrics` (JSONB — the numbers that fired the rule), `explanation` (plain language),
`false_positive_note` (required, FR-66), `detector_version`, `computed_at`.

### `risk_assessments`
`id`, `analysis_run_id` (FK), `address_id` (FK), `score` (smallint 0–100), `band`
(`LOW`|`MEDIUM`|`HIGH`|`CRITICAL`), `confidence` (NUMERIC 0–1), `signals` (JSONB — array of
`{name, raw_value, weight, points, description}`, FR-81), `config_version`,
`engine_version`, `computed_at`.
**Unique:** `(analysis_run_id, address_id)`.

`signals` is the explainability payload and is **not optional** — a row with an empty
`signals` array is invalid.

### `alerts`
`id`, `case_id`, `analysis_run_id`, `alert_type` (`SANCTIONED_CONTACT` | `MIXER_CONTACT` |
`CRITICAL_RISK` | `CROSS_CASE_MATCH`), `severity`, `address_id`, `trigger_reason`,
`source_finding_type`, `source_finding_id`, `acknowledged_by` (nullable FK users),
`acknowledged_at`, `created_at`.

---

## 7. Evidence and output

### `evidence_items`
The L0 index. Bodies live on disk/object storage; this table is the catalogue.

`id`, `case_id`, `analysis_run_id` (nullable), `evidence_type` (`API_RESPONSE` |
`REPORT` | `GRAPH_IMAGE`), `provider`, `endpoint`, `request_params` (JSONB),
`http_status`, `storage_path`, `content_sha256`, `byte_size`, `retrieved_at`, `is_fixture`
(distinguishes cached-snapshot from live, NFR-15).

Append-only. No UPDATE or DELETE from application code.

### `reports`
`id` (PK, UUID), `case_id`, `analysis_run_id`, `report_type` (`FULL` | `SUMMARY`),
`format` (`PDF` | `JSON` | `CSV`), `storage_path`, `content_sha256`, `generated_by` (FK
users), `narrative_source` (`TEMPLATE` | `LLM`), `generated_at`.

`narrative_source` is recorded so a reader knows whether prose was machine-written (FR-115).

### `audit_log`
`id` (bigserial), `actor_id` (nullable — system actions have none), `action`,
`resource_type`, `resource_id`, `case_id` (nullable, for case-scoped filtering),
`request_id`, `ip_address`, `user_agent`, `payload_sha256`, `created_at`.

**Append-only, enforced at the database level** — the application role is granted INSERT and
SELECT only, with no UPDATE or DELETE privilege on this table. Discipline in code is not
sufficient for an audit log.

---

## 8. Indexing and query requirements

The queries that actually matter, and what they need:

| Query | Index |
|---|---|
| All transfers for an address, newest first | `transfers (from_address_id, block_time DESC)` and `(to_address_id, block_time DESC)` |
| Transfers between two addresses in a window | `transfers (from_address_id, to_address_id, block_time)` |
| Transfers by tx hash (drill-down from a report) | `transfers (chain_id, tx_hash)` |
| Address lookup by string (the primary user action) | unique `addresses (chain_id, address)` |
| Cross-case correlation — which cases contain this address (FR-07) | `case_addresses (address_id)` |
| Case list with filters | `cases (owner_id, status, created_at DESC)` |
| Trace reconstruction | `trace_nodes (trace_id, depth)`, `trace_edges (trace_id)` |
| Latest profile for an address | unique `address_profiles (address_id, data_version)` |
| Attribution lookup during tracing (hot path) | `attributions (address_id, computed_at DESC)`; label lookup `address_labels (address_id)` |
| Open alerts across cases | `alerts (case_id, created_at DESC)` partial on `acknowledged_at IS NULL` |
| Audit trail for a case | `audit_log (case_id, created_at DESC)` |

**Hot path note.** During a trace, the engine asks "is this address a known service?" for every
discovered address. That lookup must be fast and is best served from an in-memory set of
labelled addresses loaded once per job, backed by `address_labels`. Doing it as a per-address
database round-trip inside the BFS loop is the most likely performance mistake in this system.

**Partitioning.** Not needed at MVP volumes (DATA_ARCHITECTURE §10). If `transfers` exceeds
~100M rows, range-partition by `block_time`. Documented, not built.

---

## 9. Integrity rules worth enforcing in the database

Not merely in application code, because these are the product's correctness guarantees:

1. `attributions`: CHECK constraint binding `tier` to its required evidence, as described in §4.
2. `risk_assessments`: CHECK that `signals` is a non-empty JSONB array.
3. `transfers`: UNIQUE `(chain_id, tx_hash, transfer_index)` — idempotent ingestion.
4. `audit_log` and `evidence_items`: application role has no UPDATE/DELETE grant.
5. `pattern_findings`: `false_positive_note` NOT NULL.
6. All monetary quantities: `NUMERIC`, never `float`/`double precision`.
7. All timestamps: `timestamptz`, stored UTC.

Rules 1, 2 and 5 exist because the honesty guarantees of this product are worth more than the
convenience of a nullable column.
