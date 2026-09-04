# User Flows

Screen-level detail: [FRONTEND_SPEC.md](FRONTEND_SPEC.md). Human process:
[INVESTIGATOR_WORKFLOW.md](INVESTIGATOR_WORKFLOW.md).

---

## Flow 1 — New case to first answer (the primary flow)

**Actor:** investigator · **Trigger:** an NCRP complaint with a wallet address ·
**Goal:** know which exchange received the funds

```
Login
  └→ Dashboard
       └→ [+ New Case]
            └→ Case details  (title, NCRP ref, loss amount, date)
                 └→ Add suspect address
                      ├→ invalid format ──→ inline error, stay
                      ├→ unsupported chain ──→ "looks like Bitcoin, not supported"
                      └→ valid
                           ├→ already in another case ──→ banner, link, continue
                           └→ [Start analysis]
                                └→ Progress screen (stages stream)
                                     ├→ failed ──→ reason + retry
                                     ├→ partial ──→ workspace with amber banner
                                     └→ complete
                                          └→ Investigation workspace, Overview tab
```

**Success:** the Overview tab states in plain language where the money went, which exchange
received it, and what to do next.
**Time budget:** under 3 minutes from login, of which under 2 is the analysis (NFR-01).

---

## Flow 2 — Quick Trace (demo path, and the impatient path)

```
Dashboard → [Quick Trace] → paste address → [Analyse]
  → provisional case created silently (audit trail preserved)
  → progress → workspace
  → [Save as case] to attach case metadata, or discard
```

Exists because an investigator with an address and a question should not have to fill a form
first. It is also the SIH demo entry point.

---

## Flow 3 — Working the graph

```
Workspace → Graph tab
  ├→ click node → detail rail: attribution, risk, profile
  │    ├→ [Expand] → subtree loads
  │    ├→ [Set as root] → new analysis from this node
  │    └→ [View on explorer] → independent verification
  ├→ drag timeline scrubber → flow replays chronologically
  ├→ adjust depth slider → re-query, graph rebuilds
  ├→ filter by asset / minimum value
  └→ click terminal node → termination reason + recommended next step
```

---

## Flow 4 — Verifying a finding (the trust flow)

The flow that decides whether an investigator believes the tool at all.

```
Any claim in the UI
  └→ expand
       ├→ risk score → signal table (name, raw value, weight, points, description)
       │    └→ signal → triggering transactions → explorer link
       ├→ attribution → evidence list
       │    ├→ CONFIRMED → dataset name, URL, dataset date
       │    └→ PROBABLE  → per-signal evidence + "also consistent with" note
       ├→ pattern → triggering transactions + false-positive note
       └→ any number → Evidence tab → raw API response + SHA-256 + retrieval time
```

Every path terminates at either a public block explorer or a stored raw response. There is no
claim in this product that dead-ends in "trust us".

---

## Flow 5 — Attribution override

```
Attribution tab → card → [Override]
  → select tier and entity
  → justification (required, cannot be skipped)
  → [Save]
       → override stored separately; machine finding remains visible
       → both appear in the report
       → audit log entry written
```

---

## Flow 6 — Report generation

```
Workspace → [Report]
  → select analysis run
  → toggle sections; pinned findings appear first
  → narrative: Template | AI-assisted
  → [Generate]
       ├→ LLM unavailable → falls back to template, response says so
       └→ complete → report ID + SHA-256 + [Download PDF]
                       previous reports remain listed and downloadable
```

---

## Flow 7 — Alert triage

```
Dashboard → alert
  → jumps directly to the causing finding inside the relevant case
  → [Acknowledge] with an optional note → audited
```

---

## Flow 8 — Cross-case correlation

```
Add address (or global search)
  → system detects the address in another case
  → banner: "Also in TF-2026-0098 (owned by another investigator)"
  → [View] → permitted only if the user has access to that case;
             otherwise shows case number and owner contact only
```

Deliberate limit: an investigator learns that an overlap exists and who to speak to, without
gaining access to another officer's case contents (NFR-08).

---

## Flow 9 — Error and degradation paths

| Situation | What the user sees | What they can do |
|---|---|---|
| Provider rate limited | *"Slower than usual — provider rate limit"*, progress continues | Wait or cancel |
| Provider down | *"<Provider> unavailable; using cached data from <time>"* | Continue with cached, or retry later |
| Analysis partial | Amber banner naming degraded stages and reasons | Use results, or re-run |
| Address never transacted | Explicit finding, not an error | Check for a typo; check other addresses in the complaint |
| Trace stops at hop 1 | *"Funds have not moved from this address"* | Act quickly — funds may still be there |
| Graph truncated | Persistent banner with node counts | Expand, or narrow filters |
| Session expired | Redirect to login preserving return path | Re-authenticate and resume |

---

## Flow 10 — External submission (FR-130)

```
External system → POST /integration/submit (API key)
  → case auto-created, marked EXTERNAL
  → analysis queued
  → 202 with status_url
  → optional callback on completion
  → the case appears in the dashboard for human review
```

**Nothing is auto-actioned.** A machine-submitted case is reviewed by a person before any
conclusion leaves the system.
