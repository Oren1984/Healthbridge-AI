# Testing strategy and evidence

## Strategy

| Layer | Where | What it proves |
|---|---|---|
| Unit (no DB) | `backend/tests/test_unit_*.py` | Upload validation, extraction, metadata, recommendation parsing (EN/HE), every care-gap rule on hand-built snapshots, FHIR mapping, chunking, embeddings, agent guardrails & tool allowlist, LLM output guard, password policy, log redaction |
| Integration (real PostgreSQL + pgvector) | `backend/tests/test_api_*.py`, `test_rag_evaluation.py` | API behaviour through FastAPI with the real database, worker processing, consent enforcement, IDOR/BOLA, revocation/expiry, meeting tokens, multi-professional approvals, handoffs, assistant (incl. mocked Ollama success/rejection/fallback), notifications, admin, audit-chain tampering, retrieval quality and authorization |
| End-to-end (Playwright, real browsers) | `frontend/e2e/*.spec.ts` | The golden scenario through the UI with separate browser sessions; real WebRTC video with 3 participants via LiveKit; denial of unauthorized access; Help Center; EN/HE + RTL; mobile layout; keyboard; axe accessibility |
| Security scanning | pip-audit, npm audit, gitleaks, Docker Scout | Dependency CVEs, secrets, image CVEs — see [security.md](security.md) |

Integration tests run in a dedicated `healthbridge_test` database (the conftest refuses any other) and reseed
synthetic data per module. E2E tests run against the full Docker stack; global setup resets demo data.
Video tests use Chromium's fake camera/microphone; the assertion is on **subscribed remote camera tracks**
reported by livekit-client, not on UI state.

## Results (executed 2026-10-16, Windows 11 + Docker Desktop)

### Backend — `148 passed, 0 failed` (~45 s)

| File | Tests |
|---|---|
| test_unit_extraction.py | 32 |
| test_unit_care_gaps.py | 16 |
| test_unit_fhir_rag_agent.py | 36 |
| test_api_auth.py | 11 |
| test_api_authorization.py | 11 |
| test_api_documents.py | 11 |
| test_api_care.py | 8 |
| test_api_consultations.py | 8 |
| test_api_assistant_admin.py | 13 |
| test_rag_evaluation.py | 2 |

One warning: Starlette deprecation notice about `httpx` in its test client (no functional impact).

RAG evaluation output: `hit@1=10/10 hit@3=10/10` (see caveats in [ai-and-rag.md](ai-and-rag.md)).

### End-to-end — `20 passed, 0 failed` (3–4 min, Chromium)

Golden scenario (`golden-scenario.spec.ts`, serial, separate browser contexts per person):

| # | Step | Result |
|---|---|---|
| 1–3 | Patient uploads the Cedar Ridge letter (PDF); 5 recommendations extracted and highlighted at their source passages; journey shows the event | ✓ |
| 4–5 | Care gap for the echocardiogram is **Unknown** with rule CG-001 and missing evidence; clarification item created and visible in Follow-ups | ✓ |
| 6–7 | Patient previews and approves sharing with Dr. Morgan; schedules a consultation with Dr. Morgan (US) and Dr. Bennett (UK); shares agenda documents with participants | ✓ |
| auth | A non-shared document returns *not found* for a participant; a non-participant professional cannot open the consultation | ✓ |
| 8–9 | Three separate sessions join the room; each sees 3 participants and ≥ 2 subscribed remote video tracks; the shared document is reviewable from the room | ✓ |
| 10–12 | Notes → summary with proposed follow-up → approved by Morgan (still pending Bennett, consensus not assumed) → approved by Bennett → acknowledged by patient; journey event becomes *Professional-confirmed*; "second opinion" referral becomes **Completed & verified** while the echocardiogram stays **Unknown** | ✓ |
| 13 | Patient's access history shows Dr. Morgan's activity; revoking her grants immediately blocks the letter | ✓ |

Application checks (`app.spec.ts`): patient/professional login, generic auth errors, demo scenario sign-in,
malicious upload rejection, FHIR upload + import report, assistant (sourced answer, diagnosis refusal,
confirmation-gated action), completion without evidence stays unverified, Help Center search/navigation/contextual
help, Hebrew/English switching (persisted, `dir=rtl`), 390 px mobile layout without horizontal overflow, skip link
and focus management, **axe scan of 9 screens with zero serious/critical violations** (WCAG 2.0/2.1/2.2 A/AA rule
tags), sample-file presence.

### Defects found by testing and fixed

* Document category taken from body text (a letter mentioning "the laboratory report" became a lab result) → heading-first classification.
* Keyword retrieval ANDed all terms → OR-query without stopwords (calibrated against seeded data).
* `Intl.DateTimeFormat` threw when combining `timeZoneName` with `dateStyle` → explicit fields; added error boundaries so one page error no longer blanks the app.
* Effect cleanup crash: `scrollIntoView` returns a Promise in current Chromium and was returned from a `useEffect` → block bodies.
* Mobile overflow (109 px) from implicit grid columns → explicit `grid-cols-1`.
* Language toggle not persisted for signed-in users → saved to profile.
* Patient access history polluted by system events → filter to people.
* LLM dose guard blocked quoted lab values ("151 mg/dL") → narrowed + regression test.
* LiveKit theme made the room header invisible → theme scoped to the video area.
* RAG chunks could start mid-word → chunk boundaries snap to whitespace (`test_chunks_start_on_word_boundaries`).
* **Care-gap detail leaked to partially-shared professionals** (found by security review): titles, recommendation
  text, suggestions, document IDs, journey-event labels and other professionals' names from sources the professional
  could not see → per-viewer `gap_view` redaction in the API and the assistant
  (`test_care_gaps_redacted_for_partially_shared_professional`); Hebrew rendering of redacted items added.
* Declined consultation participants kept access to the consultation's summary documents → participation check
  requires `invite_status != "declined"` and the professional role (found by security review).
* Signing out and signing in as a different user in the same tab sent the new user to the previous user's page
  (sign-out cleared the session while the protected route was still mounted, which recorded it as the next
  sign-in's return path) → navigate to `/login` before clearing the session. Surfaced by slow connections below.
* E2E flakiness on Windows: ports are published on `127.0.0.1` only, and `localhost` resolves to `::1` first, so every
  new browser connection waited seconds for the refused IPv6 attempt → tests default to `http://127.0.0.1:8083`.

## How to run

```powershell
# Backend unit + integration (uses the db service and a separate test database)
docker compose --profile test run --rm tests

# End-to-end (stack must be running; tests use http://127.0.0.1:8083, override with HB_BASE_URL)
cd frontend
npm ci
npx playwright install chromium
npx playwright test

# Security scans
docker compose --profile test run --rm tests pip-audit -r /tmp/requirements.txt   # Git Bash: prefix MSYS_NO_PATHCONV=1
npm audit
docker scout quickview healthbridge-backend
```

Screenshots for documentation: `cd frontend && node scripts/capture-screenshots.mjs` (resets to the showcase scenario).

## Not covered

Firefox/WebKit browsers; real devices on other networks (NAT traversal/TURN); load/performance testing;
screen-reader user testing (axe is automated and catches a subset of WCAG issues); penetration testing;
clinical validation of extraction accuracy beyond the synthetic corpus.
