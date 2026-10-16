# HealthBridge AI — Project Hand-off

**Date:** 2026-10-15 (updated 2026-10-16) · **Branch:** `feature/healthbridge-platform` (local only) · **Base:** `main` @ `8b2e951 Initial commit`
**Status:** implementation complete and verified locally, including the §0 security fix (done 2026-10-16);
**nothing committed or pushed yet** (awaiting user go-ahead).

---

## 0. Care-gap disclosure fix — DONE (2026-10-16)

* `gap_view` (`backend/app/api/serializers.py`) is the single per-viewer serializer for the care-gap list, the review
  response and the assistant's gap/question tools. Beyond the original change it now also hides: event/task evidence
  without a journey grant, consultation evidence/CG-004 titles for consultations the viewer is not in, titles of
  document-only gaps whose documents are all hidden, `documented_timeframe`, and CG-005/CG-009 evidence and
  missing-evidence lines (which named other professionals). Unknown evidence types are hidden by default.
  Redacted gaps carry `params.redacted = true`.
* Test: `test_care_gaps_redacted_for_partially_shared_professional` (API list, review, assistant, patient view unchanged).
  It caught the CG-009 missing-evidence leak.
* Frontend: `gapText.ts` renders redacted gaps in Hebrew without broken text; empty supporting evidence shows "None".
* Also fixed: sign-out race that sent the next user to the previous user's page (`Layout.tsx`), and E2E defaults
  moved to `http://127.0.0.1:8083` (ports bind IPv4 loopback only; `localhost` → `::1` cost seconds per connection on
  this machine). Documented in `docs/security.md` and `docs/testing.md`.
* Known residual (documented): follow-up task titles, visible with a journey grant, can quote recommendation text from
  unshared documents.

## 1. Where things stand (one paragraph)

The full application is built and running locally in Docker Compose: React/TypeScript frontend, FastAPI backend,
background worker, PostgreSQL + pgvector, self-hosted LiveKit, and an optional Ollama profile. Every screen in
the brief exists and works end-to-end with persistent synthetic data. The golden scenario passes as an automated
browser test, including a real three-participant WebRTC video session. All automated suites were green at the
moment of pausing. The remaining work is closing work: committing, a last documentation pass, and the final
delivery report.

## 2. Verified results (last runs, 2026-10-16)

| Check | Result |
|---|---|
| Backend unit + integration (real PostgreSQL + pgvector) | **148 passed**, 0 failed |
| E2E Playwright (Chromium), incl. 13-step golden scenario + 3-participant video | **20 passed**, 0 failed (rebuilt stack) |
| Accessibility (axe on 9 screens, WCAG A/AA rule tags) | 0 serious/critical violations |
| RAG retrieval evaluation (10 labeled queries) | hit@1 10/10, hit@3 10/10 (tiny synthetic corpus — regression guard only) |
| pip-audit · npm audit · gitleaks (tree + history) | 0 · 0 · 0 findings |
| Docker Scout, our images | backend 0 critical / 1 high · frontend 0 critical / 4 high (base OS layers) |
| Real Ollama (`qwen2.5:1.5b`, CPU) | Integration works; one cited answer validated; small model often omits citations → safe fallback (documented) |
| Docker stack | 5 services up and healthy; `/api/ready` OK |

README.md and docs/testing.md now state **148**.

## 3. What was completed

**Backend (`backend/`)** — config, models, Alembic migration `0001`, security primitives (Argon2id,
sessions with hashed tokens, CSRF, rate limits, Fernet file encryption, HMAC-chained audit), central
`AccessPolicy` (`app/authz.py`), routers for auth, documents, journey/recommendations, care gaps/tasks,
sharing/consent, consultations/summaries/handoffs, assistant, notifications (+ authenticated WebSocket),
admin, system/demo. Services: upload validation and extraction (EN/HE), FHIR R4 import/export, care-gap
engine (9 deterministic rules, replayable), RAG (chunking, hash embedder, pgvector + tsvector hybrid,
authorization before ranking), bounded agent with optional Ollama, LiveKit tokens, notifications,
deterministic seeding (`fresh` / `showcase`), and a polling worker.

**Frontend (`frontend/`)** — 18 screens: landing, login, demo scenarios, patient dashboard, journey,
documents, document detail, care gaps, follow-ups, sharing center, privacy & audit, consultations,
consultation detail with summaries, Global Care Room (LiveKit), assistant, notifications, Help Center
(17 bilingual articles + contextual help), settings, professional workspace and consented patient view,
administration. Hebrew/English with RTL, light/dark themes, responsive layout, error boundaries,
nginx with a strict CSP.

**Infrastructure** — `docker-compose.yml` (db, backend, worker, frontend, livekit, optional ollama,
test runner), multi-stage non-root images, health checks, named volumes, `.env.example`, `.gitleaks.toml`.

**Docs (`docs/`)** — architecture & API, care-gap rules, AI & RAG, FHIR, security & threat model,
privacy & regulatory matrix, testing & evidence, deployment, demo guide, known limitations,
references, and 14 real screenshots. `README.md` rewritten (WHAT / WHY / HOW).

**Decisions made during the session (with the user):** backend moved to port **8003**, web app to
**8083** — host ports 8000–8002 and 8080–8082 are taken on this machine (also saved to Claude memory).

## 4. Current runtime state

* Stack is **running** (`docker compose ps`); app at <http://localhost:8083>. Data was last reset to the
  **showcase** scenario by the screenshot script.
* Ollama container exists but is **stopped**; it holds the `qwen2.5:1.5b` model (~1 GB) in the `ollama` volume.
* Local `.env` contains generated dev secrets (gitignored; never commit).
* Test database `healthbridge_test` exists alongside `healthbridge` in the same Postgres volume.
* The Postgres image was upgraded to `pgvector 0.8.7-pg16-trixie`; collation versions were refreshed
  (`REINDEX` + `REFRESH COLLATION VERSION`) and verified at 2.41.

## 5. Where to resume — next actions, in order

0. ~~Security fix (§0)~~ — done.
1. ~~Test-count correction~~ — done (148).
2. ~~`prompt_01.md`~~ — no longer in the repo and never in git history; nothing to decide.
3. ~~Commit~~ — done 2026-10-16 as 4 local commits (not pushed; push/PR only with explicit approval). Original note: **Review the diff and commit** on `feature/healthbridge-platform` (needs user go-ahead). Do not commit
   `.env`, `frontend/e2e/.auth/`, `frontend/test-results/`, `node_modules/` (all gitignored). Suggested split:
   backend · frontend · infra · docs, or one commit. Push only if explicitly authorized.
4. **Final delivery report** (brief §34): architecture, feature inventory, status by area, test counts,
   Docker validation, screenshots, limitations, git status, run instructions — separating *verified*,
   *implemented but not fully verified*, *incomplete*, and *out of scope*.
5. Optional: `docker compose down` when finished (keep volumes), or leave running for review.

### Quick resume commands

```powershell
docker compose up -d --build                         # http://localhost:8083
docker compose --profile test run --rm tests         # backend: expect 148 passed
cd frontend; npx playwright test                     # E2E: expect 20 passed (stack must be running)
node scripts/capture-screenshots.mjs                 # regenerates docs/screenshots (resets to showcase)
```

## 6. What remains / not done (be explicit in the final report)

**Implemented but not fully verified**
* Optional `fastembed` semantic embeddings — code path exists; package not installed in the image; untested.
* Optional Ollama mode — verified only with a 1.5B CPU model; answer quality not evaluated; larger model recommended.
* Video beyond one machine — not tested across LAN/NAT or in Firefox/Safari; no TURN (coturn) shipped.

**Not implemented (documented as limitations)**
* OCR for scanned PDFs (marked "needs manual review" instead).
* AI-assisted document translation (optional in the brief; not built — originals are always shown).
* Recording/transcription (intentionally excluded); chat is ephemeral.
* Production items: TLS/WSS, KMS key management, encrypted DB volume, distributed rate limiting, MFA/real
  identity, real licence verification, malware scanning, SIEM, backups, pen-test.

**Residual risk**
* Upstream images carry base-layer CVEs: pgvector (4 critical / 33 high), LiveKit (3 critical / 12 high).
* Rule-based extraction and the small clinical vocabulary are validated only on the synthetic corpus.
* No compliance claimed (HIPAA, GDPR, Israeli privacy/patients' rights law, SaMD) — see `docs/privacy-regulatory.md`.

## 7. Definition-of-Done status (brief §33)

| Criterion | Status |
|---|---|
| All screens implemented; persistent workflows; patient & professional roles | ✅ verified |
| Unauthorized access blocked; consent & revocation | ✅ verified (API + E2E) |
| Document ingestion; evidence-based care gaps; follow-up tracking | ✅ verified |
| Multi-participant video in the supported environment | ✅ verified (3 sessions, one machine) |
| Consultation summaries; RAG respects authorization; agent within bounds | ✅ verified |
| Deterministic mode without Ollama | ✅ verified (default) |
| Hebrew & English; Help Center | ✅ verified |
| Docker startup; tests executed; security checks | ✅ verified |
| Documentation; real screenshots | ✅ done |
| Golden E2E scenario demonstrated | ✅ verified (automated, 13 steps) |
| Unauthorized data access blocked — care-gap detail for partially-shared professionals | ✅ verified (dedicated test, redeployed, E2E) |
| Committed to git / final report delivered | ✅ 4 local commits on `feature/healthbridge-platform` (backend · frontend · infra · docs), **not pushed**; final report delivered in the 2026-10-16 session |

## 8. Key file map

| Concern | Path |
|---|---|
| Authorization policy | `backend/app/authz.py` |
| Care gap engine | `backend/app/services/care_gaps.py` |
| Extraction / FHIR | `backend/app/services/extraction.py`, `fhir.py` |
| RAG / agent / LLM | `backend/app/services/rag.py`, `agent.py`, `llm.py` |
| Synthetic data | `backend/app/seed_data.py`, `services/seed.py`, `demo/sample-documents/` |
| Frontend screens | `frontend/src/pages/`, shared panels in `frontend/src/components/panels/` |
| Translations | `frontend/src/i18n/en.ts`, `he.ts`; help content `frontend/src/help/articles.ts` |
| E2E tests | `frontend/e2e/` |
| Compose / proxy / CSP | `docker-compose.yml`, `frontend/nginx/` |
