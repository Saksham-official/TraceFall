# TraceFall

**A blockchain investigation and intelligence platform that turns a victim-reported cryptocurrency wallet address into an explainable fund-flow investigation.**

**Smart India Hackathon 2026 · PS 26183 · Blockchain & Cybersecurity**
**Status: SIH 2026 shortlisted prototype**

[SIH Presentation](#resources) · [Project Demo](#resources) · [GitHub source](.)

## The problem

SIH Problem Statement 26183 asks for the real-time identification of fraud-linked cryptocurrency exchanges from victim-reported suspect wallet addresses through automated blockchain analytics.

When a bank-fraud victim reports an account number, the institution is usually identifiable from the banking route. A cryptocurrency wallet address is different: it is a pseudonymous destination, not an issuer, bank, or jurisdiction. Investigators must manually inspect public transactions, follow branches across addresses, decide which patterns matter, and determine whether a destination is an exchange deposit address.

Blockchain data is public, but:

```text
Public blockchain data  ≠  ready-to-use investigation intelligence
```

TraceFall adds that investigation layer: it converts raw transactions into fund flow, relationships, suspicious-pattern signals, possible VASP attribution, risk, and evidence.

## What TraceFall does

An investigator submits a suspect wallet reported by a victim. TraceFall then retrieves or replays blockchain data, normalizes it, follows the relevant asset across multiple hops, builds a graph, detects patterns, evaluates possible service attribution, scores risk, and produces a report that shows both findings and uncertainty.

```text
Victim-reported suspect wallet
              ↓
       Blockchain data
              ↓
       Multi-hop tracing
              ↓
     Transaction graph
              ↓
   Suspicious pattern detection
              ↓
      VASP / exchange analysis
              ↓
       Risk + confidence
              ↓
    Evidence & investigation report
              ↓
       Freeze-request support
```

The result is an investigative lead and an auditable fund-flow view — not an automatic finding of guilt and not an identification of the real-world person behind a wallet.

## Why burner wallets do not end the investigation

A burner wallet can hide a user's identity, but transactions involving that wallet remain observable on a public blockchain. TraceFall follows the movement of funds rather than assuming that the first wallet reveals the person behind it.

**TraceFall traces funds; it does not automatically identify a real-world person.** Identifying an account holder requires information held by a VASP and an appropriate legal process.

## Current prototype scope

The working demonstration primarily uses:

| Term | Meaning in this prototype |
|---|---|
| **TRON** | Blockchain network used by the primary demonstration. |
| **USDT / TRC-20** | A stablecoin transferred on the TRON network; this is the main traced asset in the demo. |
| **Ethereum** | Implemented as a second adapter for native ETH, ERC-20, and internal transactions; it is not the primary presentation path. |
| **VASP** | Virtual Asset Service Provider, such as a cryptocurrency exchange or custodial service. |

Bitcoin, Solana, BSC, Polygon, privacy coins, and automated cross-chain bridge tracing are not implemented in the current prototype.

## Investigator workflow

### 01 — Submit

The investigator creates a case and enters a victim-reported wallet address, chain, and optional reported amount/time.

### 02 — Validate

TraceFall validates the address before requesting blockchain data.

### 03 — Trace

The tracing engine follows the relevant asset across configured hops using proportional **haircut taint** tracking, depth limits, thresholds, fan-out caps, and edge budgets. A haircut is an attribution convention for pooled fungible assets, not a claim that coins can be physically separated.

### 04 — Visualize

Transfers become an interactive Cytoscape.js graph with an address list carrying the same information for readable review.

### 05 — Detect

Pattern detectors identify shapes such as fan-out, fan-in, rapid transfer/layering, peel chains, dormancy bursts, and structuring. Each is a signal with a documented false-positive mode, not proof of criminal activity.

### 06 — Attribute

TraceFall checks curated address labels and deposit-funnel behavior to determine whether a destination may be associated with a VASP or other service.

### 07 — Assess

The risk engine returns a 0–100 score, risk band, separate confidence, itemized signal contributions, and signals that could not be evaluated.

### 08 — Preserve

Raw provider responses, transaction references, findings, report metadata, and retrieval times are retained in the evidence layer. Reports are hash-verified with SHA-256.

### 09 — Act

A draft KYC/freeze-request document can be generated for investigator review. TraceFall does not send legal requests, freeze funds, recover assets, or hold private keys.

## Key features

| Capability | What is implemented |
|---|---|
| **Suspect wallet intake & validation** | Case-scoped intake with TRON and Ethereum address validation. |
| **Blockchain data ingestion** | Provider adapters, pagination, rate limiting, caching, normalization, and partial-data handling. |
| **Multi-hop fund-flow tracing** | Forward tracing with configurable depth, thresholds, fan-out caps, edge/address budgets, and explicit termination reasons. |
| **Proportional value / taint tracking** | Haircut attribution for the selected asset, with pruning and completeness signals. |
| **Interactive transaction graph** | Graph nodes and edges show addresses, transfers, risk, attribution tier, and evidence references. |
| **Suspicious pattern detection** | Fan-out, fan-in, rapid transfer, peel chain, dormancy burst, and structuring detectors. |
| **VASP / exchange attribution** | Curated label matching plus deterministic deposit-address funnel analysis. |
| **Confidence-aware attribution** | `CONFIRMED`, `PROBABLE`, and `UNATTRIBUTED` remain separate in storage, API, UI, and reports. |
| **Explainable risk scoring** | Versioned weighted rules, 0–100 score, risk band, confidence, raw values, weights, points, and unevaluated signals. |
| **Investigation history and auditability** | Case-scoped access, RBAC, append-only audit logging, and analysis history. |
| **Evidence integrity** | SHA-256 hashes for raw responses and generated reports, with retrieval/generation timestamps. |
| **Investigation reports** | PDF, JSON, and CSV outputs; the PDF includes findings, limitations, and evidence references. |
| **Freeze-request support** | Reviewable draft request text addressed to a supported service when the analysis provides an actionable attribution. |
| **Offline deterministic demo mode** | Committed provider-response fixtures replayed through the same downstream analysis pipeline. |
| **Live blockchain mode** | Opt-in provider retrieval when the required configuration/API access is available. |

## How VASP / Binance identification works

Exchange identification is based on **address attribution plus transaction behavior**, not magic and not identity resolution.

```text
Suspect wallet
      ↓
Intermediate wallets
      ↓
Potential deposit address
      ↓
Known/labeled Binance collection wallet
```

For a possible Binance deposit funnel, the system can examine signals such as:

- repeated incoming deposits;
- many counterparties;
- short holding or dwell time;
- sweep behavior into a known labeled collection wallet; and
- the consistency of the destination and its surrounding activity.

The result may be **`PROBABLE Binance`** with a confidence score and the signals behind it. A known Binance collection wallet appearing in a curated, dated first-party dataset can be **`CONFIRMED`** as that labeled address. Neither result proves that a particular person owns the upstream wallet.

Similar funnel behavior can also come from payment processors, custodial services, OTC desks, other exchanges, or automated business sweepers. Therefore TraceFall uses:

| Tier | Meaning |
|---|---|
| `CONFIRMED` | The address matches a named, dated public dataset. |
| `PROBABLE` | Behavior and/or linked labels support an inference, with confidence and evidence shown. |
| `UNATTRIBUTED` | The available data does not support a reliable attribution; the reason is shown. |

The current curated Binance dataset contains TRON wallet labels from Binance's own proof-of-reserves disclosure. It is useful first-party provenance, but it is not a complete list of Binance deposit addresses.

## Risk and pattern interpretation

The risk engine is a transparent weighted rule system configured in `config/risk_weights.yaml`:

- score range: **0–100**;
- bands: `LOW` 0–24, `MEDIUM` 25–49, `HIGH` 50–74, `CRITICAL` 75–100;
- every evaluated signal reports raw value, maximum weight, points, description, and evidence transactions;
- unevaluated signals contribute no points and reduce confidence instead of being silently treated as safe; and
- confidence is shown separately from the score.

The score is an **investigative prioritization signal**, not a probability of fraud, criminal identity, or guilt. Legitimate high-volume services, payment processors, traders, arbitrage systems, and market makers can resemble suspicious patterns.

## Evidence and reporting output

At the end of an investigation, an investigator can review:

- the connected transaction graph and text address list;
- transfer amounts, timestamps, transaction hashes, asset contract identity, and trace termination reasons;
- detected patterns with explanations and false-positive notes;
- attribution tier, entity type, confidence, source, and supporting evidence;
- risk score, band, confidence, itemized signals, and data-completeness warnings;
- PDF, JSON, or CSV investigation reports; and
- a reviewable VASP KYC/freeze-request draft where the analysis supports one.

SHA-256 demonstrates that a stored response or report file has not changed since it was recorded. It does not prove that a provider's data was truthful, create a legally recognized chain of custody, or make a report court-admissible.

## Demo cases and data provenance

The demo configuration is in [`config/demo_addresses.yaml`](config/demo_addresses.yaml). It contains TRON case seeds for a headline multi-hop trace, fan-out behavior, funds that stop moving, an honestly unattributable low-history wallet, a configured Binance-funnel showcase, and a more complex laundering-shaped flow.

The judge-facing walkthrough currently documents the measured headline, quiet-root, fan-out, and funds-not-moved cases. The Binance and laundering entries are explicit showcase configurations; their exact output must be verified with the repository's pre-flight check before presenting a particular attribution or score as a demonstrated result.

### Primary — Binance fraud trail

The intended showcase follows:

```text
Victim payment → suspect wallet → intermediary wallets
                → potential deposit address
                → labeled Binance collection wallet
```

It is designed to demonstrate the VASP attribution path and the distinction between a `PROBABLE` deposit address and a `CONFIRMED` labeled collection wallet. It is not evidence that Binance caused or participated in a fraud; it is an on-chain routing demonstration.

### Fallback — complex fund movement

The second showcase is designed to demonstrate branching, consolidation, peel-chain behavior, multiple hops, and a VASP deposit funnel. It is useful when the primary case is not suitable for the presentation environment.

### Real versus synthetic data

- The committed demo cache contains **frozen provider responses captured from public blockchain APIs** and is replayed offline. It is not live at presentation time, and the UI marks fixture/cached data accordingly.
- Test-only golden scenarios and unit fixtures are synthetic and are used to exercise algorithms deterministically. They are not presented as real fraud incidents.
- A wallet being on a public sanctions or label dataset is not, by itself, proof that a current investigation is a real fraud case.

## Live mode versus offline mode

### Live mode

With `LIVE_MODE=true` and the required provider configuration, TraceFall can retrieve supported blockchain data from TronGrid for TRON and Blockscout/Etherscan-compatible providers for Ethereum. Live runs are subject to provider completeness, API limits, response changes, and network availability.

### Offline demo mode

`LIVE_MODE=false` is the default. The application reads committed, deterministic provider-response fixtures instead of making live network/API calls. The same normalization, tracing, graph, pattern, attribution, risk, and reporting pipeline runs downstream; the final investigation result is not hardcoded.

Offline mode is for deterministic demonstrations and reliability when internet/API access is unavailable. It does not imply that production deployment must be offline.

## Architecture

```text
┌────────────────────────────┐
│ Investigator UI             │ React + TypeScript + Cytoscape.js
└──────────────┬─────────────┘
               ↓
┌────────────────────────────┐
│ FastAPI API / auth / RBAC   │ validation and case isolation
└──────────────┬─────────────┘
               ↓
┌────────────────────────────┐
│ Orchestrator + async worker │ Redis-backed pipeline
└──────────────┬─────────────┘
               ↓
┌────────────────────────────┐
│ Data adapters               │ Live providers or fixture cache
└──────────────┬─────────────┘
               ↓
┌────────────────────────────┐
│ Normalize → trace → graph  │ canonical transfers and fund flow
└──────────────┬─────────────┘
               ↓
┌────────────────────────────┐
│ Patterns → attribution      │ deterministic, confidence-aware
│ → risk                     │ intelligence
└──────────────┬─────────────┘
               ↓
┌────────────────────────────┐
│ Evidence and reports       │ PDF / CSV / JSON / request draft
└────────────────────────────┘
```

This is a modular monolith with an asynchronous worker. PostgreSQL stores case, analysis, graph, attribution, risk, audit, and report records; Redis provides queue/cache support; the evidence and report stores retain generated artifacts.

## SIH PS 26183 alignment

| SIH requirement | TraceFall implementation |
|---|---|
| Victim-reported suspect wallet | Case intake accepts and validates the reported wallet and chain. |
| Automated blockchain tracing | Provider adapters and an asynchronous multi-stage analysis pipeline. |
| Transaction graph analysis | Interactive graph plus a text representation of the same nodes and edges. |
| Fund movement analysis | Multi-hop, asset-aware tracing with proportional value attribution. |
| VASP/exchange identification | Curated address labels and deposit-funnel behavior analysis. |
| Suspicious activity detection | Fan-out, fan-in, layering, peel-chain, dormancy-burst, and structuring signals. |
| Risk categorization | Explainable 0–100 score, risk band, separate confidence, and itemized signals. |
| Actionable intelligence | Destination, stopping reason, attribution evidence, and a possible VASP follow-up target. |
| Investigation reports | PDF, JSON, and CSV report generation. |
| Evidence generation | Raw-response capture, SHA-256 hashes, transaction references, timestamps, and audit trail. |
| Scalable/multi-chain architecture | Chain adapters isolate TRON/Ethereum-specific retrieval and normalization from downstream analytics. |

## Technology stack

### Frontend

React 18, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, Cytoscape.js, Vitest, Testing Library, axe-core, and Playwright.

### Backend

Python 3.12, FastAPI, Uvicorn, Pydantic Settings, SQLAlchemy async, Alembic, PyJWT, Argon2, NetworkX, PyYAML, and ReportLab.

### Database and infrastructure

PostgreSQL 16, Redis 7, Docker Compose, and nginx-served frontend assets.

### Blockchain and data providers

TRON via TronGrid; Ethereum via Blockscout and optional Etherscan-compatible access. Curated labels are committed under `data/labels/`. No ML model ships in the current prototype; the attribution heuristic and risk engine are deterministic and inspectable.

## Attribution boundaries and limitations

TraceFall is deliberately bounded. It may have difficulty with:

- fresh wallets with insufficient transaction history;
- mixers and privacy-focused systems;
- cross-chain movement and bridge correlation;
- irregular exchange sweeps and shared deposit addresses;
- off-chain exchange activity and internal customer transfers;
- unknown services and stale or incomplete public labels;
- provider rate limits, pagination/truncation, and unavailable data; and
- swaps into another asset, because a trace follows one selected asset.

The trace can stop at a confirmed service boundary, depth/threshold/budget limit, time window, no outflow, or unavailable data. It records why it stopped rather than silently presenting a smaller answer as complete.

**A wallet receiving stolen funds is not automatically a criminal.** TraceFall identifies investigative leads and fund-flow evidence. It does not prove fraud, guilt, identity, ownership, or intent; it does not trace every cryptocurrency; and it does not replace legal process or commercial blockchain-intelligence platforms.

## Where TraceFall fits

Platforms such as Chainalysis, TRM Labs, and Elliptic already provide advanced enterprise blockchain intelligence. TraceFall is not positioned as a replacement for them.

Its focus is a narrower, practical first-level workflow: start from a victim-reported suspect wallet and guide an investigator through tracing, pattern analysis, VASP attribution, risk assessment, and evidence generation in one case-scoped application.

## Security and evidence design

Implemented safeguards include:

- case-scoped RBAC and access isolation;
- validation at API boundaries and rate limiting;
- append-only audit logging for reads and state-changing actions;
- no victim PII or KYC data stored; reference numbers are stored as references;
- raw provider responses stored with SHA-256 and retrieval metadata;
- generated reports stored with their content hash;
- explicit attribution tiers and confidence rather than collapsed guesses; and
- visible data-completeness, truncation, fixture, and limitation warnings.

These mechanisms improve reproducibility and accountability. They are not a claim of legal certification or court admissibility.

## Project status and future scope

**Implemented now:** end-to-end case intake, supported-chain ingestion, normalization, multi-hop tracing, graphing, pattern detection, VASP attribution, risk scoring, evidence capture, audit logging, reports, freeze-request drafting, live-provider configuration, and deterministic offline replay.

**Future scope:** broader Bitcoin support, deeper Ethereum and additional EVM-chain coverage, automated cross-chain correlation, richer VASP datasets, calibrated learning from reviewed investigator outcomes, production-scale indexing, and integration with government cybercrime complaint systems after the required partnership and approvals.

## Quick start

### Local Docker development

```bash
git clone <repository-url>
cd TraceFall
cp .env.example .env
./scripts/generate-secret.sh >> .env
docker compose up -d
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli load-labels
docker compose exec api python -m app.cli create-admin
open http://localhost
```

The `create-admin` command is interactive. The default `.env.example` configuration uses `LIVE_MODE=false`, so the application does not need blockchain API keys for the offline path.

### Demo mode

After the stack is running, verify the committed demo snapshot:

```bash
cd backend && pip install -e '.[dev]' && cd ..
python3 scripts/demo_fixtures.py --check
```

Use an address from [`config/demo_addresses.yaml`](config/demo_addresses.yaml) for a deterministic walkthrough. The check replays the trace through the real tracing engine and reports missing fixtures or drift in the configured expected graph size.

### Live mode

Set `LIVE_MODE=true` in `.env` and configure the provider variables documented in [`.env.example`](.env.example), such as `TRONGRID_API_KEY` and `ETHERSCAN_API_KEY` where required. Live analysis is provider-dependent and may be slower or partial because of rate limits and public-data availability.

### Developer checks

```bash
cd backend && pip install -e '.[dev]' && ruff check . && mypy app && pytest
cd ../frontend && npm ci && npm run lint && npm run typecheck && npm test
npm run e2e
```

## Resources

- **SIH Presentation:** [TraceFall team briefing PDF](TraceFall-Team-Briefing.pdf) · `[Add SIH PPT Drive Link]`
- **Project Demo:** `[Add recorded/live demo link]`
- **GitHub Repository:** [This repository](.)
- **Detailed documentation:** [Project overview](docs/PROJECT_OVERVIEW.md), [demo script](docs/DEMO_SCRIPT.md), [system architecture](docs/SYSTEM_ARCHITECTURE.md), [VASP identification](docs/VASP_IDENTIFICATION.md), [risk engine](docs/RISK_ENGINE.md), and [limitations](docs/LIMITATIONS.md).

## License

No license file or license declaration is currently included in the repository.
