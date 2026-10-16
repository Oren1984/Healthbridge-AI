# Security and threat model

Scope: the local, synthetic-data demonstration. Production gaps are listed explicitly at the end.

## Assets and trust boundaries

Assets: patient documents and extracted text, consent grants, consultation content, session tokens, audit log,
encryption keys. Boundaries: browser ↔ nginx (8083), nginx ↔ backend (internal network), backend ↔ PostgreSQL,
backend/worker ↔ encrypted volume, browser ↔ LiveKit (WebRTC), backend ↔ optional Ollama.

## Threat model (STRIDE)

| Threat | Example | Controls | Evidence |
|---|---|---|---|
| **S**poofing | credential stuffing, session theft | Argon2id hashing; generic login errors; per-IP and per-account rate limits; 5-failure lockout (5 min); opaque random session tokens stored hashed; `HttpOnly` + `SameSite=Lax` cookie (`Secure` via `HB_COOKIE_SECURE`); sessions revoked on password change/deactivation | `test_api_auth.py` |
| **T**ampering | CSRF, altered audit history, malicious uploads | CSRF token header on all unsafe methods; HMAC-SHA256 hash-chained audit log with verification endpoint; upload validation (extension allowlist, magic-byte signature, PDF active-content rejection, UTF-8/NUL checks, size limit); content never executed | `test_csrf_required…`, `test_audit_tampering_detected`, `TestValidation` |
| **R**epudiation | "I never viewed that record" | Audit entry for every view/download/list by others, sharing change, task transition, meeting token, assistant query (metadata only), and every denial; patient-visible access history | `test_denials_are_audited`, E2E step 13 |
| **I**nformation disclosure | IDOR/BOLA, cross-patient RAG, admin snooping, log leakage | Central `AccessPolicy`; 404 for invisible objects; random UUIDs; consent enforced on list/view/download/retrieval; RAG filtered by authorized IDs **before** ranking; care gaps redacted per viewer (only content from sources the professional can already see); meeting membership grants no record access; admins have no clinical endpoints; JSON log redaction; no document text/tokens/messages in logs; files Fernet-encrypted at rest; `Content-Disposition: attachment` + `nosniff` downloads; strict CSP | `test_api_authorization.py` (incl. `test_care_gaps_redacted_for_partially_shared_professional`), `test_rag_never_crosses…`, `test_rag_evaluation.py`, `test_stored_file_is_encrypted_at_rest` |
| **D**enial of service | upload floods, assistant abuse | Size limits (10 MB, nginx 11 MB); rate limits on login, register, upload, assistant, meeting join; worker retries capped at 3 | `test_rate_limit_on_login` |
| **E**levation of privilege | patient → admin, professional writing patient data | Role dependencies on every route; object-level checks per action (`require_self`); unverified professionals cannot receive grants or invitations; tool allowlist; assistant state changes need user confirmation and re-authorization | `test_role_separation`, `test_unverified_professional…`, `test_state_change_requires_confirmation` |

AI-specific: prompt injection inside documents (flagged, stripped before LLM context, never followed),
unauthorized retrieval (structurally prevented), clinical over-reach (pre-tool refusal + output validation).
See [ai-and-rag.md](ai-and-rag.md).

### Found and fixed: care-gap disclosure to partially-shared professionals (MEDIUM, 2026-10-16)

A professional granted *care gap findings* plus only some documents could see, through
`GET /patients/{pid}/care-gaps`, the review response and the assistant's gap/question answers, content derived from
sources the patient never shared with them: recommendation text and titles, suggested clarifications, timeframes,
document IDs and titles, journey-event labels (without a journey grant), consultation titles they are not part of,
and CG-005/CG-009 findings naming other professionals. Fix: `gap_view` (`backend/app/api/serializers.py`) is the
single per-viewer serializer for all three paths. Patients see the full finding. Other viewers keep the finding
itself (rule, status, missing-evidence type) but evidence is filtered to their scope, and title, suggestion and
parameters are replaced with a neutral "not shared with you" text when their source is out of scope; sharing
findings about other professionals become a generic item. Unknown evidence types are hidden by default.
Residual: follow-up task titles (visible with a journey grant) may still quote recommendation text from
unshared documents — journey/task sharing is by design all-or-nothing in this demo.

## Video (LiveKit)

* Tokens issued only to non-declined participants of `scheduled`/`in_progress` consultations, within a join
  window (2 h before start → 4 h after end); TTL 10 minutes; identity = user ID; one room; `roomRecord` and
  `roomAdmin` not granted (`test_join_tokens_are_scoped_and_short_lived`).
* Room names are random; recording/transcription is not implemented; chat uses LiveKit data messages and is not stored.
* Locally, LiveKit binds to `127.0.0.1` only. WebRTC media is DTLS-SRTP encrypted; signalling is plain `ws://` locally
  (use `wss://` with TLS in any networked deployment).

## Security headers

nginx: CSP (`default-src 'self'; script-src 'self'; connect-src 'self' <LiveKit>; frame-ancestors 'none'; object-src 'none'`),
`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
`Permissions-Policy` (camera/mic/display-capture self only), `Cross-Origin-Opener-Policy`.
API: `Cache-Control: no-store`, CSP `default-src 'none'`. CORS limited to configured origins with credentials.
`style-src 'unsafe-inline'` is required by inline style attributes (React/LiveKit components); no inline scripts are allowed.

## Supply chain and scanning (results 2026-10-15)

| Check | Tool | Result |
|---|---|---|
| Python dependencies | `pip-audit` (runtime requirements) | No known vulnerabilities |
| npm dependencies | `npm audit` (all and production) | 0 vulnerabilities |
| Secrets in tree + git history | `gitleaks` v8.29.1 with `.gitleaks.toml` | No leaks (3 test-password literals allowlisted narrowly) |
| Backend image | Docker Scout | 0 critical, 1 high (Debian base `python:3.12-slim`) |
| Frontend image | Docker Scout | 0 critical, 4 high (nginx 1.30 Alpine base) |
| `pgvector/pgvector:0.8.7-pg16-trixie` (upstream) | Docker Scout | 4 critical, 33 high — upstream base packages, not fixable here |
| `livekit/livekit-server:v1.13.8` (upstream) | Docker Scout | 3 critical, 12 high — upstream image; newer v1.13.10 not better at test time |

Image hardening done: the stale `nginx-unprivileged:1.29-alpine` pin (13 critical) was replaced by `1.30-alpine`;
images rebuilt with `--pull`; PostgreSQL moved to the trixie-based pgvector image (11 → 4 critical).
Containers run as non-root (backend UID 10001, nginx unprivileged).

Re-run: `docker compose --profile test run --rm tests pip-audit -r /tmp/requirements.txt`,
`cd frontend && npm audit`, `docker scout quickview <image>`, gitleaks per [testing.md](testing.md).

## Encryption

* **At rest (implemented):** document files are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) under a key
  from `HB_STORAGE_ENCRYPTION_KEY`; stored under random names.
* **Not encrypted at application level:** extracted text and RAG chunks in PostgreSQL (needed for search),
  database volume. Production requires volume/disk encryption and a KMS-managed key with rotation.
* **In transit:** local HTTP. Any non-local deployment must terminate TLS (HTTPS + WSS) and set `HB_COOKIE_SECURE=true`.

## Known production gaps (not addressed by this demo)

KMS/HSM key management and rotation; TLS termination and HSTS; distributed rate limiting (current limiter is
in-process — correct for one backend instance only); MFA and real identity proofing; real professional licence
verification; WAF; malware scanning (e.g. ClamAV) of uploads; centralized log/SIEM pipeline; backup and
disaster recovery; penetration testing; formal secure SDLC sign-off; append-only (WORM) audit storage —
the current log is tamper-*evident*, not tamper-*proof*; TURN server (coturn) for restrictive networks.
