# Privacy and Compliance

> **Not legal advice.** This document describes design choices intended to be privacy-respecting
> and to align with the direction of Indian data-protection and law-enforcement practice. Any
> real deployment requires review by qualified legal counsel and the deploying agency's
> compliance function. TraceFall makes **no claim of certification, accreditation, or legal
> admissibility.**

---

## 1. What data the system holds

| Category | Held? | Notes |
|---|---|---|
| Blockchain transaction data | Yes | Public by design; pseudonymous |
| Wallet addresses | Yes | Pseudonymous identifiers, not identities |
| Case metadata (title, description, loss amount, dates) | Yes | Investigation data |
| NCRP / FIR reference numbers | Yes | **Reference strings only** |
| Investigator accounts | Yes | Name, email, role, organisation |
| Audit logs | Yes | Actor, action, resource, IP, timestamp |
| Raw API responses | Yes | Evidence layer |
| **Victim name, phone, email, address, bank details** | **No** | Deliberately excluded |
| **KYC data of any kind** | **No** | Not available and not sought |
| **Any personal identity linked to an address** | **No** | Not derivable and not attempted |

**The design decision that shapes this document: TraceFall stores no victim PII.**

The NCRP reference number is a pointer. The identity behind it lives in NCRP, where it belongs
and where access controls already exist. Duplicating it here would create a second copy of
sensitive personal data with no analytical benefit — the trace does not need to know who the
victim is, only how much they sent and when.

This is not merely compliance convenience. It materially reduces breach impact: a compromise of
TraceFall exposes investigation *activity*, not victims' personal details.

---

## 2. Are wallet addresses personal data?

Honestly: **it depends, and the answer is unsettled.**

A wallet address is a pseudonymous identifier. Standing alone it identifies no one. Combined
with KYC records held by an exchange, it can identify a specific person — which is the entire
point of the investigative workflow.

Under India's **Digital Personal Data Protection Act, 2023**, "personal data" is data about an
identifiable individual. Whether an address qualifies depends on whether the holder can
reasonably identify the person. TraceFall cannot — we hold no KYC data and no means to obtain
it. An exchange receiving our report can.

**We therefore treat addresses as potentially-sensitive pseudonymous data**: access-controlled,
audit-logged, retained under a policy, and never published. Treating them as public because
they appear on a public ledger would be technically defensible and practically wrong.

The DPDP Act contains exemptions for processing in the interests of prevention, detection,
investigation, and prosecution of offences, subject to conditions. **Whether and how those
exemptions apply to a specific deployment is a legal question for the deploying agency, not a
question this design can answer.** We build to be defensible either way.

---

## 3. Data minimisation

Applied concretely, not as a slogan:

- **No victim PII.** §1.
- **Reference numbers, not records.** NCRP and FIR references are opaque strings; the system
  never fetches or stores the underlying complaint.
- **Bounded retrieval.** Tracing fetches what the trace needs within the configured window, not
  an address's entire history where that is avoidable.
- **No speculative collection.** We do not crawl or index the chain. Data is retrieved
  case-by-case, in response to an investigative need.
- **No third-party enrichment of persons.** No social media, no name lookups, no OSINT
  aggregation. The system analyses transactions, not people.

---

## 4. Retention

| Data | Default retention | Rationale |
|---|---|---|
| Case data | Life of the case + 3 years after closure | Aligns with typical investigation record-keeping; configurable per deployment |
| Evidence (raw responses) | Same as the case | Must outlive the report that cites it |
| Derived results (traces, scores) | Same as the case | Recomputable, but a report must remain explicable |
| Audit logs | Case retention + 2 years | Oversight outlives the investigation |
| Cached provider data | 1 hour (live mode) | Performance only |
| User accounts | Until deactivated; audit references retained | Audit integrity |

**Retention is configurable, and the default is a starting point, not a recommendation.** The
deploying agency's record-retention rules govern. Deletion is a documented administrative
action that cascades correctly and writes an audit entry; there is no silent purge.

---

## 5. Access control and purpose limitation

Access is role-based and case-scoped ([SECURITY.md](SECURITY.md) §3). Beyond that, three
policy commitments:

1. **Case isolation by default.** Investigators see their own and assigned cases. Broad access
   is an `ADMIN`/`ANALYST` grant, not a default.
2. **Reads are audited.** Who viewed which case is recorded, because access to investigation
   data is itself sensitive.
3. **Purpose limitation.** The system is built for investigating reported cybercrime. It is not
   a surveillance tool and has no feature for monitoring addresses absent a case — a design
   constraint, not just a policy statement. Adding continuous monitoring
   ([FUTURE_SCOPE.md](FUTURE_SCOPE.md)) would require a deliberate decision with its own
   safeguards.

---

## 6. Evidence handling and what we do not claim

**What we do.** Store raw provider responses immutably with SHA-256 hashes and retrieval
timestamps. Hash generated reports. Maintain an append-only audit trail enforced by database
grants. Record data sources and retrieval times in every report. Provide explorer links so any
finding can be independently verified.

**What we explicitly do not claim.**

- ❌ That our evidence handling constitutes a legally recognised chain of custody.
- ❌ That reports are admissible in any court.
- ❌ That hashes constitute a digital signature or certification under the IT Act.
- ❌ That findings are forensically certified.
- ❌ That the system satisfies any specific regulatory standard.

**What is true:** the system produces reproducible, verifiable, well-documented technical
analysis of public blockchain data, with its sources and methods disclosed. Whether that is
admissible, and in what form, is determined by courts and by the procedures of the agency using
it. Overstating this would be both dishonest and, in a competition judged partly on domain
credibility, self-defeating.

---

## 7. Fairness and the risk of harm

An analytical tool used in law enforcement can cause real harm through false positives. The
mitigations are structural, not aspirational:

- **The three-tier attribution model** exists precisely so a heuristic is never mistaken for a
  fact ([VASP_IDENTIFICATION.md](VASP_IDENTIFICATION.md)).
- **Risk scores are explicitly not probabilities of guilt**, and say so wherever they appear.
- **Every finding is traceable to raw transactions**, so it can be challenged.
- **Pattern findings disclose their own false-positive modes** (FR-66).
- **Probable victims are labelled `VICTIM_SOURCE`, never as suspects.** An address paying into
  a scam wallet is almost certainly another victim; mislabelling one as a participant would
  cause direct harm to an innocent person.
- **Human decision-making is required.** No automated action results from any finding.
- **Investigator overrides are recorded** with justification, keeping human judgement visible
  and accountable.

---

## 8. Third-party data and licensing

TraceFall depends on public blockchain APIs and public address-label datasets.

**Obligations we accept:** respect each provider's terms of service and rate limits; use only
datasets whose licence permits our use; attribute sources in the UI and in reports; never
redistribute a dataset in violation of its licence.

**Concretely:** several block explorers permit API access under terms that **prohibit bulk
scraping of their label data**. TraceFall uses their APIs for transaction data as permitted,
and sources address labels only from datasets with explicit permissive licences. Every dataset
in [DATA_SOURCES.md](DATA_SOURCES.md) records its licence, and confirming those licences before
ingestion is an open item in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) (OQ-07) — not something to be
assumed during implementation.

**Disclosure to providers.** Querying a provider for an address tells that provider we are
interested in it. This is an unavoidable property of third-party APIs and is documented as a
limitation, with a self-hosted node as the mitigation path.

---

## 9. Compliance context, stated carefully

**FIU-IND registration.** Since the March 2023 PMLA notification, entities dealing in virtual
digital assets in India are required to register with FIU-IND as Reporting Entities. This is
relevant to TraceFall in one specific way: **for a registered VASP there is an identifiable,
addressable counterparty**, which makes an identified exchange actionable rather than merely
interesting. Where our curated entity data records registration status, we surface it (FR-77);
where we do not know, we say we do not know.

**SAHYOG** demonstrates that structured, automated dispatch of official requests to private
platforms is an established mechanism in the Indian context. TraceFall's request-payload
assembly is designed with that model in mind. **We do not integrate with SAHYOG and do not
claim to.**

**Mutual legal assistance.** Requests to foreign-domiciled exchanges typically require formal
channels. TraceFall prepares technical content; it does not initiate legal process, and
jurisdiction is surfaced as information for the investigator rather than as a recommendation.

---

## 10. If this were deployed for real

Beyond what the MVP builds, a genuine deployment would need: a formal privacy impact
assessment; legal review of the DPDP position for the deploying agency; a defined data-sharing
agreement covering reports leaving the system; an incident-response plan; role definitions
approved by the agency; periodic access reviews; and an independent security assessment.

Listing these is not a disclaimer. It is the honest gap between a hackathon prototype and an
operational law-enforcement system, and knowing precisely where that gap lies is part of what
makes the prototype credible.
