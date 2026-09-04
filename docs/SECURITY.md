# Security

Security is a first-class requirement, not a hardening phase. This system holds active criminal
investigation data.

---

## 1. Threat model

**What we protect.** Ongoing investigation details (which addresses are under scrutiny, and by
whom), case metadata linking references to blockchain activity, evidence integrity, provider
API credentials, and investigator accounts.

**Who we protect against.**

| Actor | Motivation | Primary control |
|---|---|---|
| **The subject of an investigation** | Learning they are being traced, and moving funds | Authentication, case isolation, no public surfaces |
| Opportunistic attacker | Any exposed system | Standard web hardening |
| Insider (over-broad access) | Curiosity or misuse | RBAC, case isolation, audit logging |
| Credential thief | API key resale | Server-side-only secrets |

**The threat that shapes the design:** a scammer learning their address is under analysis moves
the funds within minutes. Confidentiality of *which addresses are being investigated* is the
system's most sensitive property — more sensitive than any individual finding.

**Explicitly out of scope:** nation-state adversaries, physical security, and the security of
third-party providers. Note the corollary in §8: querying a public API for an address tells
that provider we are interested in it.

---

## 2. Authentication (NFR-08)

- **Passwords:** Argon2id (memory-hard). Minimum 12 characters, checked against a common-password
  list. Never logged, never returned, never included in any error.
- **Tokens:** short-lived JWT access tokens (15 min) plus rotating refresh tokens (7 days),
  stored server-side so they can be revoked. Access tokens carry `sub`, `role`, `exp`, `jti`.
- **Refresh token delivery — as built.** Login and refresh set the refresh token in an
  `httpOnly`, `SameSite=Lax`, `Path=/api/v1/auth` cookie named `tracefall_refresh`, and
  `Secure` whenever `ENVIRONMENT=production` (off in development so local HTTP works). This is
  what makes §9 achievable: the browser keeps tokens in memory only, and still survives a page
  reload, because `POST /auth/refresh` with an empty body reads the cookie and returns a full
  token pair. The token is *also* still returned in the response body, so non-browser clients
  are unaffected — the cookie is additive. `SameSite=Lax` is the CSRF defence: a cross-site
  `POST` does not carry the cookie. Flags and rationale: [API_SPEC.md §2](API_SPEC.md).
- **Login responses are identical for unknown user and wrong password.** Distinguishing them
  enumerates accounts.
- **Rate limiting:** 5 attempts per account per 15 minutes, plus a per-IP limit. Exponential
  lockout.
- **Session termination:** logout revokes every refresh token for the user *and* clears the
  cookie; password change revokes all.
- **MFA:** TOTP, `SHOULD` priority — appropriate for a system holding investigation data, and
  built if Phase 12 allows.

**No default credentials, ever.** First run requires an admin account to be created via a CLI
command. A seeded `admin/admin` in a demo build is the most likely way this project embarrasses
itself, and the setup path must make it impossible.

---

## 3. Authorization

**Roles.**

| Role | Capability |
|---|---|
| `ADMIN` | User management, system configuration, all cases |
| `INVESTIGATOR` | Full CRUD on own and assigned cases |
| `ANALYST` | Read across cases; run analyses; no case mutation. Also the API-key role |
| `VIEWER` | Read assigned cases only |

**Case isolation** is enforced at the query layer, not by hiding UI elements: every case-scoped
query filters by ownership or assignment. A user requesting a case they cannot access receives
**404, not 403** — a 403 confirms the case exists, which leaks that an investigation into a
given address is underway.

**Object-level checks on every request.** A valid token for user A must never return user B's
case, whatever the URL says. This is tested explicitly (see
[TESTING_STRATEGY.md](TESTING_STRATEGY.md)).

**Cross-case correlation exception (Flow 8).** An investigator is told that an address appears
in another case, and who owns it — case number and owner only, never contents. The overlap is
operationally essential; the contents are not.

---

## 4. Secret management (NFR-06)

- All secrets from environment variables or a mounted secrets file. **Never in source, never in
  git, never in a Docker image layer.**
- `.env.example` lists variable names with empty values and is the only env file committed.
- `.gitignore` covers `.env*` except `.env.example`, model artefacts, and evidence storage.
- Secrets are never logged. The logging configuration redacts keys matching
  `*_KEY|*_SECRET|*_TOKEN|*_PASSWORD` at the formatter level, so a careless `log.info(config)`
  cannot leak one.
- Blockchain provider API keys are used **server-side only**. The frontend never holds one and
  never talks to a provider directly.
- A pre-commit secret scanner (gitleaks or equivalent) runs in CI.

**TraceFall holds no private keys and never will.** It is read-only against blockchains. There
is no signing code, no wallet, and no code path that could move funds — which removes the
entire class of risk that makes most crypto software dangerous.

---

## 5. Input validation (NFR-07)

Validation happens at the API boundary, before any logic, using Pydantic models. Nothing
downstream re-validates or trusts a raw string.

**Address validation is a security control, not merely a UX nicety.** Address strings flow into
database queries, external API calls, file paths (evidence storage), and report generation. An
unvalidated address is an injection vector into four subsystems. Validation is strict format
checking with checksum verification ([BLOCKCHAIN_ANALYTICS.md §2](BLOCKCHAIN_ANALYTICS.md)),
applied before any use.

**Also validated:** numeric ranges (depth ≤ 10, limits capped), enum values, date ranges, UUID
format, pagination bounds. Free-text fields are length-capped and stored as text — never
interpolated into SQL, never rendered as HTML.

**SQL:** parameterised queries exclusively, via the ORM. No string-built SQL anywhere.

**File paths:** evidence storage paths are constructed from server-generated UUIDs, never from
user input. Path traversal is impossible because user input never reaches a path.

**SSRF:** the `callback_url` on `/integration/submit` is the one place a user supplies a URL.
It is validated against an allowlist, rejects private and loopback address ranges, and is
called from a restricted egress path.

---

## 6. API security

- **HTTPS only** in any deployed environment; HSTS enabled.
- **CORS** restricted to the configured frontend origin. Never `*`.
- **Rate limiting** per user and per IP; analysis creation limited more tightly than reads,
  because it is the expensive operation.
- **Request size limits** to bound resource use.
- **Security headers:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, and a restrictive CSP.
- **Error responses never leak internals.** A 500 returns a code and a request ID; stack traces
  go to logs only.
- **API keys** for `/integration/submit` are hashed at rest, scoped, revocable, and separately
  rate-limited.

---

## 7. Audit logging (NFR-09)

Every state-changing action, **and every case read**, writes an `audit_log` row: actor, action,
resource type and ID, case ID, request ID, IP, user agent, and timestamp.

Reads are audited too, deliberately. In an investigation system, *who looked at which case* is
itself security-relevant.

**Append-only, enforced by database grants** — the application role has INSERT and SELECT on
`audit_log` and nothing else ([DATABASE_DESIGN.md §9](DATABASE_DESIGN.md)). Application-level
discipline is not sufficient for an audit log; a bug or a compromised code path would silently
defeat it.

Audit logs are retained for the life of the case plus the retention period, and are exportable
for oversight.

---

## 8. Evidence integrity (NFR-10)

- Raw provider responses are hashed (SHA-256) at retrieval and stored immutably.
- Generated reports are hashed; the hash is recorded in the `reports` row and printed in the
  report itself.
- `evidence_items` is append-only by database grant, like `audit_log`.
- Any party can re-verify a report by hashing the file and comparing.

**What this does and does not prove.** It proves the file has not changed since generation, and
that our record of what a provider returned is internally consistent. It does **not** prove the
provider returned truthful data, and it is not a legally recognised chain of custody. Claiming
otherwise would be an unsupported legal claim — see
[PRIVACY_AND_COMPLIANCE.md](PRIVACY_AND_COMPLIANCE.md).

**Operational security note.** Querying a public API for an address discloses interest in that
address to the provider. This is unavoidable with third-party APIs and is a genuine
counter-intelligence consideration for sensitive investigations. It is documented in
[LIMITATIONS.md](LIMITATIONS.md); the mitigation — a self-hosted node — is in
[FUTURE_SCOPE.md](FUTURE_SCOPE.md).

---

## 9. Frontend security

- No secrets in client code or bundles.
- Tokens in memory with refresh via an httpOnly cookie; **not** in `localStorage`, which is
  XSS-readable.
- React escapes by default; `dangerouslySetInnerHTML` is not used. Addresses and labels from
  external datasets are rendered as text — a label dataset is third-party content and is
  treated as untrusted.
- CSP restricting script sources.
- Session timeout with a warning, and re-authentication on sensitive actions.

---

## 10. Dependency and supply-chain hygiene

Pinned versions with lockfiles. `pip-audit` and `npm audit` in CI. Dependencies reviewed before
addition — per the engineering principles in `CLAUDE.md`, a dependency must earn its place.
Container images pinned by digest and rebuilt on base-image security updates.

---

## 11. Deployment security

Containers run as a non-root user with a read-only root filesystem where practical. PostgreSQL
and Redis are not exposed outside the compose network. Database credentials are
environment-injected. Backups are encrypted at rest. Debug mode and API documentation
endpoints are disabled in production builds.

---

## 12. Security testing (Phase 12/13)

- Authentication bypass attempts on every endpoint.
- **Case isolation:** user A attempting every operation on user B's resources — the single most
  important test suite in the system.
- Injection attempts through address fields, search, and free text.
- Rate-limit verification.
- Secret-scanning in CI.
- Dependency vulnerability scan.
- Verification that error responses leak nothing.
- Verification that no default credentials exist in any build.
