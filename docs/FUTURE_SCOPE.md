# Future Scope

Post-SIH direction, ordered by value-to-effort. Nothing here is an MVP commitment.

---

## Tier 1 — Highest value

### 1. Bitcoin support
**Why:** UTXO chains give us the **common-input-ownership heuristic** — the strongest wallet
clustering signal in blockchain forensics, and something no account-model chain can offer
([PROBLEM_ANALYSIS.md §7](PROBLEM_ANALYSIS.md)). It would materially upgrade our clustering from
behavioural guesswork to structural inference, and Bitcoin remains significant in ransomware
and darknet cases.
**Effort:** High — a different data model end to end: inputs/outputs, change-address detection,
no account balances. The adapter interface already accommodates it (`normalize()` returns
transfers; a UTXO transaction simply produces more of them), but tracing needs a UTXO-aware path.
**Depends on:** nothing in the MVP changing.

### 2. Automated cross-chain bridge correlation
**Why:** bridge-hopping is a standard evasion, and today our trace stops at the bridge.
**How:** match an outbound bridge deposit to an inbound mint on the destination chain by
amount, timing, and recipient, emitting a `PROBABLE` link with confidence.
**Effort:** Medium-high. **Risk:** batching and aggregator contracts make correlation genuinely
error-prone — this must ship as `PROBABLE` with visible evidence, never as a seamless
continuation of the trace.

### 3. Feedback loop from investigator overrides
**Why:** every override is a human-verified label — precisely the training data we lack, and the
only realistic path out of the classifier's bootstrapping circularity
([LIMITATIONS.md §7](LIMITATIONS.md)).
**Effort:** Low mechanically, **high in care**: confirmation bias, adversarial or careless
overrides, and drift all need handling. Requires review before a label enters training, and
versioned datasets so a model change is always attributable.

### 4. Campaign-level multi-case analysis
**Why:** twenty complaints funnelling into three consolidation addresses is one criminal
operation, not twenty cases. For I4C this is the difference between processing complaints and
dismantling a network.
**How:** cross-case graph over the shared address index the system already builds, with shared
chokepoint detection.
**Effort:** Medium. **Prerequisite:** a meaningful corpus of cases.

---

## Tier 2 — Strong value, moderate effort

### 5. Additional EVM chains (BSC, Polygon, Arbitrum, Base)
Each is one adapter (NFR-17). BSC first — it is the most common evasion destination from TRON.
Low effort each; the real cost is label curation per chain.

### 6. Continuous address monitoring
Watch addresses from open cases and alert when dormant funds move — turning a closed-for-now
case into an actionable one at the moment it becomes actionable.
**Requires** the event-driven architecture noted in
[SYSTEM_ARCHITECTURE.md §7](SYSTEM_ARCHITECTURE.md), and — importantly — **explicit purpose
limitation and safeguards**, since continuous monitoring is a materially different privacy
posture from case-scoped analysis ([PRIVACY_AND_COMPLIANCE.md §5](PRIVACY_AND_COMPLIANCE.md)).

### 7. Self-hosted blockchain nodes
Removes rate limits (the system's actual bottleneck), removes provider dependence, and removes
the disclosure of our interest in an address to a third party
([SECURITY.md §8](SECURITY.md)).
**Cost:** significant storage and operational overhead. Justified at production scale, not
before.

### 8. Structured VASP request generation
Generate the complete information package an exchange requires for a KYC/freeze request,
formatted per that exchange's stated law-enforcement process, ready for an officer to send
through the proper channel.
**Note:** generation only. The system never sends anything.

---

## Tier 3 — Valuable at operational scale

### 9. Live NCRP / CFCFRMS integration
The natural end state: a crypto complaint arrives at NCRP, TraceFall analyses it automatically,
and an investigator receives a prepared case.
**Blocked on** government partnership and clearance — entirely outside our control, which is
why the MVP ships an integration-ready surface and claims nothing more.

### 10. Multi-tenancy across agencies
Data isolation per agency with controlled cross-agency correlation — technically
straightforward, organisationally and legally complex.

### 11. Advanced clustering research
Better behavioural clustering for account-model chains: gas-funding graphs, timing-correlation
analysis, contract-interaction fingerprints. Genuinely open research territory, with real
upside for the weakest part of our current analysis.

### 12. Model improvements
Once real labelled data exists (via #3): better classifiers, calibrated probabilities, and
possibly graph-based features — but only with explainability preserved. The constraint from
[AI_ML_STRATEGY.md](AI_ML_STRATEGY.md) does not relax with scale.

---

## Tier 4 — Nice, not urgent

Mobile/tablet interface for field use · report templates per agency · localisation into Indian
languages · bulk historical case re-analysis as labels improve · a public API for other
government systems · training mode with synthetic cases for investigator onboarding.

---

## Deliberately never

| Not building | Why |
|---|---|
| Identity resolution from chain data | Not possible. Claiming it would be fraud |
| Automated legal action | Every legal step requires human authority |
| Guilt or fraud determination | Judicial function |
| Fund seizure or movement | Requires legal authority and exchange cooperation; the system holds no keys |
| Privacy-coin "tracing" | Not possible; anyone claiming it is selling something |
| Surveillance without a case | Purpose limitation is a design constraint, not a policy note |
| Predictive policing of any kind | Wrong on the merits and outside this problem statement |
