# OQ-15 · Which real addresses does the demo use

*Research note. Resolves OQ-15 and fixes the contents of
[`config/demo_addresses.yaml`](../../config/demo_addresses.yaml).*
**Screened:** 2026-09-06, against live TronGrid.
**Reproduce:** `python scripts/demo_fixtures.py --check` replays the chosen set offline; the
screening itself is described in §2 and is a single TronGrid call per address.

---

## Verdict

Four OFAC-designated TRON addresses, all with real USDT-TRC20 flow inside the default
ninety-day window, covering the headline multi-hop trace, a fan-out, a funnel, and — the one
that matters most — an address the system honestly cannot identify.

| Address | Role | In the window | What the trace does |
|---|---|---|---|
| `TUcjuVB6RFvsMgE352Kdc3VHvFvteti97B` | headline | 21 in, 20 out to 6 destinations | 24 addresses, 27 edges, reaches a second OFAC-designated address, ends `MAX_DEPTH` |
| `TWBAPzpPiZarfVsY2BLXeaLhNHurn4wkWG` | fan-out | 7 in, 15 out to 9 destinations | 2 addresses — eight of the nine branches fall below the 1% taint threshold |
| `TLFqEhiG7RUSZ9x5iph99Ke5782dkgRnWf` | funds not moved | 7 in, 6 out to 2 destinations | 2 addresses, ends `NO_OUTFLOW` |
| `TXoVNrqm11FFVKcF1vEND64gibVkr1HwAR` | honestly unattributable | 3 in, 1 out | root `UNATTRIBUTED`, but the trace still follows 5 addresses into high-volume services |

---

## 1. Why OFAC designation is the provenance

OQ-15 asks for addresses "publicly documented as fraud-linked". The candidates were the 281
TRON addresses in `data/labels/ofac_sanctioned.json` — designated by the US Office of Foreign
Asset Control, extracted nightly from the SDN list, each with a designation date.

That is the strongest provenance obtainable without private law-enforcement data, and it is
checkable by anyone in the room: the address is on a published government list. The
alternative — an address from a blog post about an incident — would require the audience to
trust a compilation, which is the same objection that closed ADR-018 unadopted.

**What the designation does not say** is that this specific address defrauded a specific
victim. It says a sanctioned party controls it. The demo narrates it as what it is.

---

## 2. How they were screened

A random sample of 40 of the 281 (seed 20260906, fixed) was fetched from TronGrid's TRC-20
transfer endpoint twice: once unfiltered, once bounded to the last 90 days — the window an
analysis uses by default. For each address: inbound count, outbound count, distinct
destinations, and the token symbols involved.

Selection was on shape, not on outcome. Nothing was run through the pipeline first, so no
address was chosen because it happened to produce a flattering score.

---

## 3. The finding that shaped the choice: sanctioned addresses are dormant

**Only 5 of the 40 sampled had any outflow at all in the last ninety days.**

The other 35 were not empty — they were receiving **address-poisoning dust**. The token
symbols tell the story on their own:

> `TG: jieuu` · `ha138 com` · `unfreeze` · `Tg ip292`

These are zero-value token transfers whose *symbol* is an advertisement, sprayed at addresses
that appear on public lists. A sanctioned address is a magnet for them. Two or three such
transfers, and nothing else, was the single most common profile in the sample.

Unfiltered, most of these addresses had hundreds of real USDT transfers. Bounded to the
window, they had none: **the money moved long before the designation became public, and the
address has been dead since.** That is not a defect in the sample, it is what sanctioned
addresses look like.

Three consequences, all of which are the honest ones:

1. **The demo does not widen its window to find activity.** It runs at the ninety-day default,
   because that is what an investigator would run, and the addresses chosen are the ones that
   have something to show at that setting.
2. **Fixtures are captured over the same ninety days the demo requests**, so the committed
   snapshot and the window agree exactly. Capturing a wider slice was tried and abandoned: it
   multiplied the committed data several times over for pages the demo never reads.
3. **This belongs in the answer to "why not use a fresher address?"** — a live fraud address is
   not published anywhere at the moment it matters. The gap between when funds move and when an
   address becomes publicly known is the reason the product exists, and it is worth saying.

---

## 4. `TXoVNrqm11FFVKcF1vEND64gibVkr1HwAR` — the address that earns the rest

Three transfers in, one out. The deposit heuristic requires more behaviour than that, so the
system reports `UNATTRIBUTED` with reason `INSUFFICIENT_ACTIVITY` and states what would be
needed to go further.

This is not a weak case included for balance. It is the **measured norm**: recall on the
deposit heuristic is 0.186, and roughly four in five real deposit addresses have too little
history to classify ([OQ-09](OQ-09-deposit-heuristic-precision.md)). A demo showing only the
three that worked would misrepresent the system by a factor of five.

It is also the claim that survives questioning. A judge who asks "what happens when it does not
know?" has already been shown the answer.

---

## 5. What the traces cost, and why the fixtures are gzipped

The headline trace runs into a cluster of service addresses — 10,756, 19,987 and 9,757
transfers inside the window, each of them hitting the 10,000-per-method retrieval cap. All
four demo traces together are **800 provider responses and about 100,000 transfers**.

Uncompressed that is roughly 190 MB of committed JSON; gzipped it is 27 MB, and the
decompression cost is invisible next to the parsing that follows. That is why
`ingestion/fixtures.py` stores `.json.gz`.

It is also the reason to keep the trace bounded. A fund flow that reaches a service does
not become more informative by being followed further — the addresses past an exchange hot
wallet are other customers — and the depth, taint, edge and address budgets are what stop
this from being an unbounded crawl. The headline trace ends at `MAX_DEPTH`, and the demo
says so rather than implying the money stopped there.

---

## 6. What this set does not contain

**No address in the set is known to terminate at an exchange we can name.** OQ-15 asked for at
least one that does, and it is not promised here, because whether the trace reaches a labelled
wallet depends on `data/labels/` coverage — 405 OFAC addresses and 17 Binance TRON wallets from
Binance's own proof-of-reserves disclosure. That is thin coverage of a large chain, and saying
"the trace ends at Binance" when the labels happen not to cover the wallet it ends at would be
the exact failure this system is built to avoid.

What the demo shows instead is the `PROBABLE` deposit-address inference with its confidence and
its evidence, and where a label match happens, the `CONFIRMED` tier beside it. If a run does
reach a labelled Binance wallet, `scripts/demo_fixtures.py` prints it during capture and the
walkthrough can name it. Adding more exchanges — each from that exchange's own disclosure, via
`scripts/curate_exchange_labels.py` — is the way to change this, not relabelling what is here.
