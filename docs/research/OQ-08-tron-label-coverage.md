# OQ-08 · TRON exchange hot-wallet label coverage

*Research note. Not an ADR. Resolving OQ-08 and part of OQ-07 requires an ADR written on top of
this.*
**Researched:** 2026-09-05. All API checks in §4 were executed on that date from this machine.

---

## Verdict

**Coverage is thin but manual curation is viable — comfortably so.** ADR-001 (TRON-first) does
not need reconsidering on label-coverage grounds.

One public source (Dune's `spellbook` repository on GitHub) already lists **151 TRON addresses
across 30 named exchanges**, including Binance, OKX, HTX, Bitget, Bybit, KuCoin, Gate.io, MEXC,
and — significantly for the Indian-user requirement — **CoinDCX (13 addresses)**. Its licence
almost certainly forbids us from *ingesting* it (§3), but it is a usable *lead list*, and every
address on it can be independently verified in seconds against two free, unrestricted APIs. That
verification run is done and reported in §4: **94 of the 151 stand up to a behavioural or
second-source check, spanning 28 exchanges** — well past the 50–100 target.

---

## 1. What exists

| Source | URL | Licence | TRON coverage | Last updated | Usable? |
|---|---|---|---|---|---|
| **Dune `spellbook` — `cex_tron_addresses.sql`** | [github.com/duneanalytics/spellbook](https://github.com/duneanalytics/spellbook/blob/main/dbt_subprojects/hourly_spellbook/models/_sector/cex/addresses/chains/tron/cex_tron_addresses.sql) | **BSL 1.1** (Dune Analytics AS) | **151 addresses, 30 exchanges** — the only substantive TRON exchange-label set found | File last touched 2026-01-28; 134/151 rows added 2024-04-19, 7 added 2025-08-19 | **No — not as a dataset.** Additional Use Grant excludes our use case (§3). Yes as a **lead list** for independent re-verification |
| **OFAC SDN — `sdn_advanced.xml`** | [treasury.gov](https://www.treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.xml) · [list page](https://home.treasury.gov/policy-issues/financial-sanctions/specially-designated-nationals-and-blocked-persons-list-sdn-human-readable-lists) | US Government publication | Yes — entries are tagged `Digital Currency Address - TRX` | Continuously, by OFAC | **Yes.** Sanctions only, not exchanges |
| **`0xB10C/ofac-sanctioned-digital-currency-addresses`** | [github.com/0xB10C/…](https://github.com/0xB10C/ofac-sanctioned-digital-currency-addresses) | **MIT** (confirmed via GitHub API) | Extractor covers `TRX`; per-asset lists regenerated nightly on the `lists` branch | Pushed 2026-08-25 | **Yes.** Use it as the OFAC parser rather than writing our own |
| **TronScan API `addressTag`** | `https://apilist.tronscan.org/api/account?address=…` | **Could not confirm** (§3) | Authoritative-feeling entity tags, e.g. `Binance-Cold 2`, `Okex 4`, `Bitget 7` | Live | **Manual cross-check only.** Do not ingest |
| Kaggle *All labelled TRON addresses in transcan* (`c0mm4nd`) | [kaggle.com/datasets/…](https://www.kaggle.com/datasets/c0mm4nd/all-labelled-addresses-transcan) | **`"Unknown"`** — Kaggle's own metadata reports `license.name = "Unknown"` | Bulk TRON tags, 2.4 MB zip | **2023-10-05**, v1 only | **No.** Unknown licence *and* self-described as a bulk copy of "tronscan official tag" |
| `dawsbot/eth-labels` | [github.com/dawsbot/eth-labels](https://github.com/dawsbot/eth-labels) | MIT (repo) | **None** — EVM chains only | Pushed 2026-07-10 | **No.** Wrong chain; and the README states the data originates from Etherscan, which our own [DATA_SOURCES.md §1](../DATA_SOURCES.md) already rules out |
| `tradezon/cex-list` | [github.com/tradezon/cex-list](https://github.com/tradezon/cex-list) | **None** (no LICENSE file → all rights reserved) | **None** — repo contains only `data/ethereum-mainnet.json` | Pushed 2023-07-27 | **No** |
| `ImMike/crypto-wallet-address-labels` | [github.com/ImMike/…](https://github.com/ImMike/crypto-wallet-address-labels) | MIT | **None.** README lists "Tron (TRX) address labels" as *wanted contributions* | Created and pushed 2026-03-08 (5 stars, 1 commit) | **No** |
| `maccheroncelli/TRON-USDT-CHECKER` | [github.com/maccheroncelli/…](https://github.com/maccheroncelli/TRON-USDT-CHECKER) | **None** (no LICENSE file) | Ships a DB "pre-filled with Binance TRON/USDT Hotwallets as of January 14, 2024" | Pushed 2024-01-14 | **No.** No licence, stale, single-exchange |
| TronGrid | `https://api.trongrid.io/v1/accounts/{address}` | Per existing assessment in [DATA_SOURCES.md §1](../DATA_SOURCES.md) | No labels — balances, resources, TRC-20 holdings | Live | **Yes**, for verification. Works with no API key (confirmed 2026-09-05) |
| Dune `labels.cex` via Dune API | [dune.com/blog/labels-v2](https://dune.com/blog/labels-v2) | Dune platform ToS | The Tron model carries `post_hook='{{ hide_spells() }}'` (commit *"bulk hide curated datasets (#9245)"*, 2026-01-28) — i.e. Dune has moved these labels behind curation | 2026-01-28 | **Not pursued.** Adds a paid-platform dependency to the load-bearing data path |

**Nothing else was found.** GitHub repository search for TRON address-label datasets returned no
additional maintained sources; the search API rate-limited on the final attempt, so this sweep is
good but not exhaustive.

### For comparison — Ethereum

Same repository, `cex_evms_addresses.sql`: **4,957 addresses across 328 exchanges**
([file](https://github.com/duneanalytics/spellbook/blob/main/dbt_subprojects/hourly_spellbook/models/_sector/cex/addresses/chains/cex_evms_addresses.sql)).
So TRON coverage is roughly **3%** of EVM coverage by address count and **9%** by exchange count.
The gap is real and is exactly what OQ-08 anticipated — but 151 addresses is not "materially
thin", it is *three times* what the project said it needs, and it is concentrated on the
exchanges that matter.

---

## 2. TronScan / TronGrid label data

- **TronScan does expose entity tags through an API, not only the website.**
  `GET https://apilist.tronscan.org/api/account?address={T…}` returns `addressTag` (and
  `addressTagLogo`). Verified live: `TWd4WrZ9wn84f5x1hZhL4DHvk738ns5jwb` → `"Binance-Cold 2"`.
  Documented endpoints live at `docs.tronscan.org/api-endpoints/account`.
- **It is not a bulk/label endpoint.** There is no documented "list all tagged addresses" call.
  Labels come one address at a time, which is fine for verification and useless for seeding.
- **API keys are becoming mandatory.** TronScan has published announcements on
  [mandatory API keys for all requests](https://support.tronscan.org/hc/en-us/articles/48411600548121-Announcement-on-Mandatory-Requirement-of-API-Key-for-All-Requests)
  and on
  [rate limits without a key](https://support.tronscan.org/hc/en-us/articles/20506296714521-Announcement-on-without-an-API-key-access-frequency-limitations).
  Consistent with that, `apilist.tronscanapi.com` returned **401** for `/api/accountv2` and
  `/api/search/v2` on 2026-09-05, while `apilist.tronscan.org/api/account` still answered without
  a key. Treat unauthenticated access as temporary.
- **TronGrid needs no key** for `GET /v1/accounts/{address}` (confirmed). This is the safe
  primary verification path since we already hold TronGrid under assessed terms.

---

## 3. Licence findings (OQ-07)

### May use

**OFAC SDN.** A United States Government publication; freely reproducible. The extraction tool
`0xB10C/ofac-sanctioned-digital-currency-addresses` is **MIT** (confirmed via the GitHub API
`license.spdx_id`) and its README confirms TRX is among the covered assets and that lists are
regenerated nightly on the `lists` branch. **Ingest.**

**TronGrid.** Transaction and account data, per the existing assessment in DATA_SOURCES.md §1.
No labels involved, so no OQ-07 exposure.

### Must not use

**Dune `spellbook` — the blocker.** The repository is licensed under
[Business Source License 1.1](https://github.com/duneanalytics/spellbook/blob/main/LICENSE),
Licensor *Dune Analytics AS*, Licensed Work *Spellbook 3.0.0*. The Additional Use Grant reads, in
full:

> You may make use of the Licensed Work, provided that you may not use the Licensed Work for a
> Data or Analytics Platform.
>
> A "Data or Analytics Platform" is an offering that allows third parties (other than your
> employees and contractors working on your behalf) to access the functionality or outputs of the
> Licensed Work (including the ability to execute calculations or generate data-based insights),
> either directly or indirectly through any other tool or program.

TraceFall is an analytics offering that lets third parties (investigators) access data-based
insights. If the TRON label rows are treated as part of the Licensed Work, **ingesting that file
is squarely inside what the grant excludes.** The base BSL terms permit copy, modification and
redistribution only for *non-production* use. Change Date is **2027-03-03**, after which
Spellbook 3.0.0 converts to **GPL-3.0-or-later** — which would then impose copyleft rather than
solve the problem.

> **The distinction that matters.** A blockchain address and the identity of its operator are
> *facts*, and facts are not copyrightable. The BSL covers the compilation, not the underlying
> reality. So: **do not ingest the file; do use it to decide which addresses to look at**, then
> establish each label independently from TronScan/TronGrid observation and record *that* as the
> provenance in `label_sources`. This distinction is the whole basis of §5's plan and it is a
> legal judgement call — **it belongs in an ADR with a named decision-maker, not in a commit
> message.** If the project wants zero exposure, the alternative is §5's from-scratch path, which
> costs roughly one extra working day.

**Kaggle `c0mm4nd/all-labelled-addresses-transcan`.** Kaggle's own dataset metadata reports
`"license": {"name": "Unknown"}`. Per DATA_SOURCES.md §7 ("Any dataset with unclear licensing —
not worth the risk"), that alone disqualifies it. It is also self-described as a MongoDB export of
TronScan's `address_tag` field, i.e. a bulk copy of explorer label data — the exact thing
DATA_SOURCES.md §6 forbids. Last updated 2023-10-05.

**`tradezon/cex-list`** and **`maccheroncelli/TRON-USDT-CHECKER`.** Neither has a LICENSE file.
GitHub's API returns `license: null` for both. No licence granted means all rights reserved.

**`dawsbot/eth-labels`.** MIT on the repository, but the README states the labels come from
Etherscan. An MIT licence applied downstream does not cure upstream provenance. Ethereum-only in
any case.

### Unclear — record as unclear

**TronScan's terms of service.** *Could not confirm.* The terms are at
`https://tronscan.org/#/contracts/terms`, a client-side SPA route with no server-rendered
content. Direct fetches of `tronscan.org`, `docs.tronscan.org` and `support.tronscan.org` from
this machine were all returned **HTTP 403 by Cloudflare**. Attempted: WebFetch on the docs root
and the API-key announcement, `curl` with a browser User-Agent on three hosts, and targeted web
searches for the terms text — none returned the document body. **Someone must open that page in a
browser and read it before any TronScan-derived label is written to `label_sources`.** Until then
TronScan is a *manual verification aid used by a human*, never an ingestion source.

---

## 4. Verification spot-check

Two things were checked: (a) can a determined person confirm these are exchange wallets from
public data alone, and (b) does the Dune list actually hold up.

### (a) Named addresses, observed directly

All four confirmed against **both** TronGrid (`/v1/accounts/{addr}`, no key) and TronScan
(`/api/account?address=`), 2026-09-05:

| Address | Dune says | TronScan `addressTag` | Observed |
|---|---|---|---|
| `TCz47XgC9TjCeF4UzfB6qZbM9LTF9s1tG7` | OKX 1 | `Okex 4` | **17,179,337 txs** (6.75 M in / 10.43 M out) — unambiguously a hot wallet |
| `TAa8e7U7seCy7NcZ52xYVQXXybFfwvsUxz` | Bitget 1 | `Bitget 7` | 865,611 txs, 864,924 in / 687 out — a **collection** wallet: overwhelmingly inbound, the exact sweep destination the §4 heuristic in VASP_IDENTIFICATION.md needs |
| `TWd4WrZ9wn84f5x1hZhL4DHvk738ns5jwb` | Binance 3 | `Binance-Cold 2` | **2,061,293,347 TRX**, only 4,354 txs — a *cold* wallet, huge balance, low activity |
| `TMuA6YqfCeX8EhbfYEg5y7S4DqzSJireY9` | Binance 2 | `Binance-Cold 1` | 2,086 txs, 1,989 in / 97 out, ~35 TRX balance — dormant |

**Answer to (a): yes, comfortably.** Two independent free sources agree on the operator, and the
transaction profile is self-evidently that of an exchange. Note the last two rows: **Dune's
"Binance 3" is a cold wallet, not a hot wallet.** The list conflates roles, and
VASP_IDENTIFICATION.md §2 depends on that distinction — the sweep destination of a deposit address
is a *hot/collection* wallet, never a cold one. Role must be assigned by us from behaviour, not
copied from the source.

### (b) Full cross-verification of all 151 Dune TRON rows

Every address was queried against TronScan's `/api/account` (~90 seconds total, 0.35 s spacing,
no key). Results:

| Outcome | Count |
|---|---|
| TronScan `addressTag` names the **same** exchange | **37** |
| TronScan has **no tag** for the address | 98 |
| TronScan names a **different** exchange | 2 |
| API rejected the address as malformed | 9 |

**Two disagreements**, both real findings:
- `TEPSrSYPDSQ7yXpMFPq91Fb1QEWpMkRGfn` — Dune `MEXC`, TronScan `MXC`. Same venue, old name. Benign.
- `TSFvf8LZuwy4BKNPdULFD5vaCFMrkiGRme` — Dune `MaskEX`, TronScan `UEEx Hot Wallet 4`. **Genuine
  conflict between two different exchanges.** Exactly the case FR-75 exists for; must not be
  ingested as `CONFIRMED` under either name.

**Nine addresses are not valid TRON addresses at all.** Independently confirmed with a local
base58check implementation (not just the API's 400):

| Address | Dune label | Failure |
|---|---|---|
| `TMZisPgBCYSAgkUn1kVG7MePc9rvMEjoRN` | Binance 11 | bad checksum |
| `TCEM5YJJSYGW2RCXYXGE4SXLSPUUEJKQAW` | Binance 13 | bad checksum |
| `TUAg5gcjbcsVUiVzeDv85xLZRLad1GiQTN` | OKX 12 | bad checksum |
| `TwsBSqwEEgtKMnhcLDnJowP6YpJUTEykMV` | OKX 13 | wrong address-type prefix |
| `TjAQmFFRmVqtnkceGvLJrMwUPgCUfLjciu` | OKX 14 | wrong address-type prefix |
| `T3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHB` | Backpack 1 | wrong address-type prefix |
| `TzEc71KxDpsmsKoucSSuuoGLv1drys1oP2` | Backpack 2 | wrong address-type prefix |
| `T5vcsZtqYT3i7wAtjNPCTEGNbUmgL4ym9u` | Bitfinex 1 | wrong address-type prefix |
| `T1tgaYZzEkFpnPvyqttmPRJxbGbR4uDx49` | Bitfinex 2 | wrong address-type prefix |

That is a **6% corruption rate in a source that carries per-row attribution and dates**, and
spellbook has a prior commit titled *"remove addresses with invalid base58 characters (#8477)"* —
so this is a known, recurring defect. **A base58check validator on every ingested TRON address is
mandatory,** independent of which source is used.

**Twenty-one rows have fewer than 100 lifetime transactions** — including 9 of the 13 CoinDCX
rows, one of which has **zero**. Those are not hot wallets and must not be labelled as such.

### The set that actually survives

Filtering to rows that are either second-source corroborated **or** show ≥10,000 lifetime
transactions:

> **94 addresses across 28 exchanges** — AAX, B2BinPay, Bidesk, Binance, BitVenus, Bitfinex,
> Bitget, Bitpanda, Bitso, Bybit, **CoinDCX**, CoinEx, CoinW, Dex-Trade, Fastex, Gate.io, HTX,
> Hotbit, Klever Exchange, KuCoin, LAToken, Lemon Cash, MEXC, MaskEX, OKX, Stex, WOO X, XT.com.

Every exchange named in the OQ-08 brief is present except Huobi under that name (it appears as
**HTX**, its current name, with 18 rows).

---

## 5. Manual curation assessment

**Effort: 4–6 hours of one person's time for 60–80 verified addresses.** Confidence: high — the
mechanical half of that work is already done above and is reproducible in ~90 seconds.

**Method** (each address gets all five steps; the whole point is that no single source is trusted):

1. **Candidate generation.** Take the Dune file as a lead list of addresses to *look at*. Also
   generate leads independently: for each major exchange, take a known-good address, pull its
   counterparties from TronGrid, and inspect the high-degree ones. Cross-check against
   exchange-published proof-of-reserves address disclosures where they exist — OKX for instance
   [publishes its on-chain wallet addresses](https://www.okx.com/en-us/proof-of-reserves), which
   is the best possible provenance because it is first-party.
2. **Validate.** base58check. Reject on failure, no exceptions.
3. **Observe behaviour** via TronGrid: transaction counts, in/out ratio, TRX and USDT-TRC20
   balances. Assign **role** ourselves — hot / collection / cold — from the observed shape, and
   never carry a role over from the source.
4. **Corroborate the entity** from at least two independent public sources: TronScan
   `addressTag`, an exchange's own disclosure, or a published incident report. **Any address with
   one source only, or with conflicting sources, is `PROBABLE` at best — never `CONFIRMED`.**
5. **Record provenance** in `label_sources`: the URLs actually consulted, the observation date,
   the role we assigned, and the reasoning. Not "imported from Dune".

**Where the time goes:** roughly 1 h scripting steps 2–3 (mostly written already), 3–4 h of human
judgement on step 4 (the part that cannot be automated and is the entire value), 1 h writing
provenance.

**Confidence in the outcome: high.** 94 candidates already pass a mechanical filter; the target is
50–100; a human rejecting half of them still lands in range, and the survivors will be the
highest-volume wallets at the largest exchanges — which is exactly where fraud proceeds go.

---

## 6. Recommendation for Phase 7a

1. **Do not reconsider ADR-001.** TRON label coverage is sufficient. Ethereum's advantage is real
   but it is an advantage in *breadth*, and breadth is not what this product needs.
2. **Ingest OFAC first**, via `0xB10C/ofac-sanctioned-digital-currency-addresses` (MIT). Small,
   authoritative, unambiguous, and it exercises the whole `label_sources` path end to end.
3. **Write the ADR resolving OQ-07 before curating anything.** It must state, in the project's own
   words: Dune spellbook is a lead list and is never ingested; TronScan is a human verification
   aid and is never ingested; provenance recorded is what we observed, not where we got the idea.
   Whoever signs it accepts the §3 facts/compilation reasoning.
4. **Read the TronScan terms of service in a browser** and record the finding. This is the one
   thing this research could not do, it takes ten minutes, and it gates step 3.
5. **Add base58check validation to the ingestion path now**, not later. A 6% invalid rate was
   measured in the best available source.
6. **Curate 60–80 addresses by the method in §5**, prioritising: Binance, OKX, HTX, Bitget, Bybit,
   KuCoin, Gate.io, and **CoinDCX** — the last because an Indian exchange endpoint on an Indian
   fraud trace is the most persuasive single result the demo can produce.
7. **Assign role explicitly on every row.** The deposit-address inference in
   VASP_IDENTIFICATION.md §4 sweeps *to* hot and collection wallets. A cold wallet in that
   position produces a confident wrong answer, and the best public source demonstrably conflates
   the two.
8. **Fold OQ-15 into this work.** `TSFvf8LZuwy4BKNPdULFD5vaCFMrkiGRme` — the MaskEX/UEEx conflict —
   is a ready-made honest demonstration of FR-75 (conflicting labels, both surfaced), and the
   OFAC TRX designations are the natural source for the demo's fraud-linked addresses.

---

## Reproducing this

Nothing here needs an API key.

```sh
# behavioural profile
curl -s "https://api.trongrid.io/v1/accounts/TCz47XgC9TjCeF4UzfB6qZbM9LTF9s1tG7"

# entity tag (unauthenticated access may stop working — see §2)
curl -s "https://apilist.tronscan.org/api/account?address=TCz47XgC9TjCeF4UzfB6qZbM9LTF9s1tG7"

# the lead list
curl -s "https://raw.githubusercontent.com/duneanalytics/spellbook/main/dbt_subprojects/hourly_spellbook/models/_sector/cex/addresses/chains/tron/cex_tron_addresses.sql"
```
