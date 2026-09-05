# Demo script

The walkthrough, its timings, and the answers to the questions it invites.

**Total: six minutes of demo, leaving the rest for questions.** The addresses are the four
in [`config/demo_addresses.yaml`](../config/demo_addresses.yaml); the claims are bounded by
[LIMITATIONS.md §13](LIMITATIONS.md). Nothing said here goes beyond what the screen shows.

---

## 0. Before the room — pre-flight

Run in order. Every step has failed at least once during development, which is why each is
a step rather than an assumption.

```bash
docker compose up -d                                    # five containers, wait for healthy
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli load-labels   # 422 labels, sources printed
docker compose exec api python -m app.cli create-admin  # interactive
python scripts/demo_fixtures.py --check                 # every hop has a fixture
open http://localhost
```

`--check` is the one that matters. It replays every demo trace **offline through the real
tracing engine** and exits non-zero naming any address whose fixture is missing. A missing
fixture does not crash the demo — it shows `DATA_UNAVAILABLE`, honestly — but it shows a
gap where the fund flow should be.

Then, in the browser, before anyone is watching:

- **Sign in once** and leave the tab on the case list. The first analysis of a session is
  the slowest.
- **1366 × 768**, the projector's likely resolution. Check both themes with the toggle in
  the header; the demo runs in whichever reads better on the projector.
- **Turn the network off and reload.** `LIVE_MODE=false` is the default and the stack makes
  no outbound call, but proving it to yourself beforehand is what lets you say it flatly.

---

## 1. The problem — 45 seconds

*Say it before touching the screen.*

> When a citizen reports a bank fraud, the account number tells the investigator which bank
> to send the freeze request to. When the same citizen reports a **crypto** fraud, the
> wallet address they hand over encodes nothing at all. No issuer, no routing, no
> jurisdiction. So the investigator opens a block explorer, clicks through transactions by
> hand, and gives up after two hops — six to twelve hours, usually ending in "unknown",
> long after the money has been withdrawn.

> TraceFall answers one question: **where did the money go, and which exchange do I send the
> freeze request to?**

---

## 2. Intake — 45 seconds

New case → title → **Continue to address** → paste `TUcjuVB6RFvsMgE352Kdc3VHvFvteti97B` →
**Add address** → **Start analysis**.

While the address validates, say what it is:

> This is a real address, designated by the US Office of Foreign Asset Control. It is on a
> published government list — you can check it. We did not invent it, and we did not pick
> it because it gave a good answer; we picked four by shape before running any of them.

Point at the **cached snapshot** banner, which is on every screen:

> Everything here is real chain data, frozen. The system is running with no network at
> all. It says so on every page, because a demo that quietly pretends to be live is the
> first thing I would distrust.

---

## 3. The pipeline — 30 seconds

The progress page names each stage as it runs: retrieval, normalization, tracing, graph,
patterns, attribution, risk.

> Seven stages, about ninety seconds against this cached snapshot. Live, against a
> rate-limited free API tier, it is slower — TronGrid gives us half a request per second
> per method without a key, and we measured that rather than guessing.

**Do not say** "ninety seconds for any address, live". See §7.

---

## 4. The findings — 3 minutes

**Open findings.**

### Overview (20 s)
The plain-language answer: where the money went, and how much of it is accounted for.

### Graph (40 s)
> Every node is an address, every edge a real transaction with its hash. Fill colour is the
> risk band, border style is the attribution tier — solid for confirmed, dashed for
> probable. And there is a text list beside it carrying the same information, because a
> picture alone is not evidence and not everyone can read one.

If anything was pruned or truncated, point at it:

> It tells you what it did not follow. A smaller answer that pretends to be a complete one
> is the failure mode we designed against.

### Attribution (50 s) — **the answer to the problem statement**
> Three tiers, never collapsed: `CONFIRMED` means a named, dated dataset says so.
> `PROBABLE` means behaviour says so, with a confidence number and the signals behind it.
> `UNATTRIBUTED` means we do not know, and it says what would be needed to find out.
>
> The database has a CHECK constraint on that column. It is not a convention we remember to
> follow.

Expand one row so the evidence is on screen: the source, its date, the transactions.

### Patterns (25 s)
> Fan-out, fan-in, rapid layering, peel chains, dormancy bursts, structuring. Each finding
> carries **its own false-positive note** — the detector says how it can be wrong, in the
> same panel. Registering a detector without that note raises an error; it is enforced.

### Risk (25 s)
> Nought to a hundred, and every signal that contributed is listed with its raw value, its
> weight and its points. Confidence is reported **beside** the score, never multiplied into
> it. And there is a line under it saying this is not a probability of fraud, because it
> is not one.

If a group reads `not evaluated`, that is the point:

> Not evaluated is not zero. A confirmed exchange hot wallet has its behavioural signals
> switched off with a stated reason — otherwise the system would flag the exchange as the
> criminal.

### Evidence (20 s)
**Generate PDF report** → the report appears with its SHA-256 → download it.

> Every raw API response is stored with its hash and the time it was retrieved. The report
> hashes its own content. An investigator can show where any number came from, down to the
> stored response.

---

## 5. The address it cannot identify — 60 seconds

**This is the most important minute of the demo. Do not cut it for time.**

Run `TXoVNrqm11FFVKcF1vEND64gibVkr1HwAR` — three transfers in, one out.

> `UNATTRIBUTED`, reason `INSUFFICIENT_ACTIVITY`. Not a failure — the correct answer. And
> not a rare one: we measured the deposit-address heuristic against 2.3 million addresses
> Binance publishes as its own. **Precision 0.989. Recall 0.186.** Roughly four in five
> real deposit addresses have too little history to classify, and every one of those comes
> back exactly like this.
>
> A missed identification costs an investigator time. A wrong one sends a legal request to
> the wrong institution. We took that trade deliberately.

---

## 6. Close — 20 seconds

> On-chain tracing ends where legal process begins. The system's job is to get the
> investigator to that boundary in ninety seconds instead of a day, with an evidence trail
> that survives being questioned — and to be explicit about the point where it stops.

---

## 7. Questions, and the answers that hold

Every "can say" below is checkable on the screen or in a research note. Every "cannot say"
is a claim to refuse even when it would be easier to nod. The full table is
[LIMITATIONS.md §13](LIMITATIONS.md).

**"Is this AI?"**
> No model ships. The deposit-address classifier was planned, scoped as optional, and cut —
> the deterministic heuristic already delivers the attribution, and a model would replace an
> explainable answer with an approximate one. Every number on screen is computed by a rule
> you can read. That is a deliberate decision, written down as an ADR, not an omission.

**"How accurate is it?"**
> Precision 0.989 at the 0.7 threshold, against Binance's own published deposit addresses,
> with Binance's hot and cold wallets as deliberately hard negatives. **Recall 0.186.** The
> second number is the honest one and it never travels without the first. And it is an
> Ethereum measurement, because Binance publishes no TRON deposit addresses at all — we
> checked rather than assumed.

**"Can it identify who is behind the address?"**
> No. Nothing in public chain data supports that, and the system never claims it. It
> identifies the *service* that received the funds, which is the institution you send the
> KYC request to.

**"Is this evidence I can take to court?"**
> No. It is an investigative report with a full evidence trail — hashes, timestamps, and the
> raw responses. Whether it is admissible is a question for a court, and we do not answer
> it on the system's behalf.

**"Is it integrated with NCRP / CFCFRMS / FIU-IND?"**
> No. It exposes an integration-*ready* API. Claiming an integration we have not built would
> be the easiest thing in this room to disprove.

**"Ninety seconds — really?"**
> Against this cached snapshot, yes. Live, retrieval is bounded by the provider's rate
> limit: TronGrid without an API key sustains about half a request per second per method,
> measured. With a key it is faster. The pipeline is not the bottleneck; someone else's free
> tier is.

**"Why not trace further than three hops?"**
> It stops for stated reasons, and it tells you which: depth, taint below the threshold, a
> confirmed service boundary, no outflow, budget, window, or data unavailable. Past an
> exchange hot wallet the downstream addresses are other customers — following them is
> wrong, not merely expensive.

**"Why is this address on the list if it did nothing recently?"**
> Because sanctioned addresses go quiet. We screened forty OFAC-designated TRON addresses
> and **only five had any outflow in the last ninety days** — the rest receive nothing but
> address-poisoning dust. The money moves long before an address becomes public, which is
> exactly the gap this product exists to close.

**"What if the data is wrong or incomplete?"**
> Then it says so. Partial retrieval, pruned branches, truncated graphs and unavailable
> hops all surface in the interface and in the report. The system never quietly returns a
> smaller answer.

---

## 8. If something breaks

| Symptom | Do this |
|---|---|
| A container is unhealthy | `docker compose ps`, then `docker compose restart <service>`. The worker waits for the schema rather than dying; give it ten seconds. |
| An analysis fails with "no fixture" | An address outside the committed set was entered. Use one from `config/demo_addresses.yaml`; that is what `--check` guarantees. |
| The graph canvas does not render | The address list below it carries the same information. Read from that; it is not a fallback bolted on for the demo, it is how the page works without a canvas. |
| Nothing loads at all | Switch to the recording. Do not debug in front of the room. |

**Record the full walkthrough beforehand and have it one keystroke away.** A recording that
is never played costs five minutes; a stack that will not start with an audience waiting
costs the presentation.
