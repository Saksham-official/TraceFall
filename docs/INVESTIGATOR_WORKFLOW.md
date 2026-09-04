# Investigator Workflow

The human process, end to end, and where automation actually saves effort.

---

## 1. The workflow today, without TraceFall

What an investigator with a crypto address in an NCRP complaint currently does:

| Step | Manual effort |
|---|---|
| Open a block explorer, paste the address | 2 min |
| Read the transaction list, identify the victim's transfer | 10–30 min |
| Follow outgoing transfers by clicking through, one address at a time | **2–6 hours** for 3–4 hops |
| Try to work out whether any destination is an exchange | 30 min–hours, usually inconclusive |
| Manually record hashes, amounts and timestamps in a document | 1–2 hours |
| Write the report | 2 hours |
| **Total** | **6–12 hours per address, frequently ending in "unknown"** |

And the honest outcome: most investigators stop after one or two hops, because clicking through
a fan-out of forty addresses by hand is not feasible, and because there is no reliable way to
tell whether address `TQn9…` is an exchange.

**The consequence is not just slowness.** By the time an answer emerges, the funds have been
withdrawn. The golden hour that CFCFRMS protects for bank fraud is simply lost for crypto.

---

## 2. The workflow with TraceFall

| Stage | Who | Effort | Automated? |
|---|---|---|---|
| 1. Receive complaint, extract address | Human | 2 min | No — reading a complaint is human work |
| 2. Create case, enter address + amount + time | Human | 3 min | No — audit anchor |
| 3. Retrieve, normalize, trace, graph, detect, attribute, score | **System** | **90 s** | **Fully** |
| 4. Review findings, verify key claims | Human | 10–20 min | Assisted |
| 5. Decide next action | Human | 5 min | Assisted (recommendation given) |
| 6. Generate report | System | 15 s | Fully |
| 7. Send request to the identified VASP | Human | 15 min | Assisted (request payload assembled) |
| **Total** | | **~45 min** | |

**6–12 hours → ~45 minutes, and a materially better answer**, because the system follows every
branch rather than the two an analyst has patience for.

---

## 3. Stage detail

### Stage 1 — Complaint intake (human)

Read the complaint, extract the wallet address, and — critically — the **amount and the
date/time the victim sent funds**. These two fields are frequently present in a complaint and
frequently ignored. They anchor the trace to the victim's actual transaction rather than to
everything the address ever did ([WALLET_TRACING.md §2](WALLET_TRACING.md)).

Also worth capturing: screenshots of the scam platform, the payment instruction the victim
received, and any other addresses mentioned.

*Not automated, and should not be. Interpreting a distressed complainant's account is human
work.*

### Stage 2 — Case creation (human, 3 min)

Case metadata, then the suspect address with amount and time. Validation is immediate. If the
address is already in another case, the investigator learns now.

*Deliberately kept human: the case is the audit anchor for everything that follows.*

### Stage 3 — Automated analysis (system, ~90 s)

Everything in the pipeline: retrieval, normalization, enrichment, tracing, graph construction,
pattern detection, attribution, risk scoring, alerts.

**This is where the six hours go.** The investigator watches a progress list or works something
else in the meantime.

### Stage 4 — Review (human, 10–20 min)

The investigator reads the Overview narrative, then works the graph and verifies the claims
that matter:

- Does the highest-value path make sense?
- Is the exchange attribution `CONFIRMED` or `PROBABLE`? If `PROBABLE`, does the evidence
  actually support it?
- Do the pattern findings hold up against their own false-positive notes?
- Is any of the data marked incomplete?

*Assisted, not automated. Judgement stays with the person accountable for it.*

**The system's job here is to have prepared the case so well that review takes twenty minutes
instead of a day.**

### Stage 5 — Decide (human, 5 min)

The decision tree the Overview tab supports directly:

```
Funds reached a CONFIRMED exchange address
  → request KYC + freeze from that exchange, naming address, hashes, times, amounts

Funds reached a PROBABLE exchange address
  → verify the evidence
  → if convinced: request, noting the basis is behavioural
  → if not: continue tracing, or seek corroboration

Funds reached a mixer
  → on-chain trail ends; document thoroughly; pursue other case avenues

Funds reached a bridge
  → note destination chain; a separate analysis is needed there

Funds have not moved
  → act fast, these are the recoverable cases

Nothing attributable
  → document what was traced; preserve for cross-case correlation;
     re-run later — funds may move, and labels improve over time
```

That last branch matters. An unattributed case is not a closed one; it is a case waiting for
either the funds to move or the label datasets to improve.

### Stage 6 — Report (system, 15 s)

Sections selected, pinned findings first, generate, download. Report ID and SHA-256 recorded.

*Fully automated. This alone replaces roughly two hours of manual document assembly.*

### Stage 7 — Act (human, 15 min)

Send the request to the identified VASP. The Attribution tab has already assembled the payload
an exchange will ask for: the deposit address, the transaction hashes, timestamps, amounts, and
the case reference.

*The legal request itself is human work through the appropriate channel. TraceFall prepares the
technical content; it does not send anything to anyone.*

---

## 4. Where automation genuinely saves effort

| Task | Manual | Automated | Why it matters |
|---|---|---|---|
| Multi-hop tracing | 2–6 h | 60 s | **The single biggest win.** Manual tracing is infeasible past a fan-out |
| Exchange identification | 30 min–∞ | instant | **The PS26183 answer.** Manually near-impossible for deposit addresses |
| Pattern detection | rarely attempted | instant | Humans do not spot a 47-way split across 400 transactions |
| Evidence assembly | 1–2 h | automatic | Also removes transcription errors |
| Report writing | 2 h | 15 s | |
| Cross-case correlation | not done at all | instant | Only feasible with a shared address index |
| Victim enumeration (backward trace) | not done at all | 30 s | Turns one complaint into a campaign picture |

The last two are capabilities that simply do not exist in the manual workflow at any effort
level.

---

## 5. Where the human must stay

- **Interpreting the complaint.**
- **Judging a `PROBABLE` attribution before acting on it.** The system presents evidence; a
  person decides whether it is enough to justify a legal request.
- **Deciding investigative direction.**
- **Every legal step.** TraceFall produces technical findings, not legal process.
- **Any conclusion about people.** The system reports addresses and flows, never identities.

---

## 6. Multi-investigator and supervisory use

**Cross-case correlation** flags an overlapping address and names the other case's owner,
without exposing that case's contents.

**Supervisory triage:** sort open cases by risk band and by "funds have not moved", which is
the population where action can still recover money.

**Campaign view (future):** when several cases funnel into common consolidation addresses, that
is one operation, not five complaints. Identifying it requires the cross-case index this system
builds as a side effect. See [FUTURE_SCOPE.md](FUTURE_SCOPE.md).

---

## 7. What the investigator must never conclude from TraceFall alone

Printed in every report and stated in the UI:

1. That an address belongs to a specific person. **Never inferable from this system.**
2. That a `PROBABLE` attribution is confirmed.
3. That a high risk score is evidence of a crime.
4. That an unattributed address is innocent, or that an attributed one is guilty.
5. That the absence of a finding means the absence of activity — data may be incomplete, and
   the system says when it is.
