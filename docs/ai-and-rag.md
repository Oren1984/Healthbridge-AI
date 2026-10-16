# AI agent and RAG design

## Scope

One bounded, tool-based assistant for **administrative and informational continuity support**
(`backend/app/services/agent.py`). It is not a clinical decision-support system.

| Allowed | Prohibited (enforced in code) |
|---|---|
| Retrieve authorized documents and quote passages | Diagnosis, prescribing, doses, treatment changes |
| List open follow-ups and unresolved care gaps | Accessing records the user is not authorized to see |
| Summarize journey events | Sending information outside HealthBridge |
| Suggest administrative questions | Executing arbitrary code or tools |
| Point to help articles | Modifying approved clinical records |
| *Propose* a follow-up task (inert until confirmed) | Closing tasks or changing status on its own |

## Control flow

```mermaid
flowchart TD
  Q[User message] --> G{Guardrails<br/>clinical / external-send patterns}
  G -- match --> R[Refusal, no tools run]
  G -- ok --> I[Intent router<br/>deterministic patterns, EN + HE]
  I --> T{Tool allowlist}
  T --> S[search_documents]
  T --> L[list_care_gaps / list_followups / journey_summary / suggest_questions / help_navigation]
  T --> P[propose_followup_task → AssistantAction 'pending']
  S --> A[AccessPolicy.accessible_document_ids<br/>BEFORE retrieval]
  A --> X[Hybrid retrieval, SQL-filtered]
  X --> M{AI mode}
  M -- mock --> D[Template answer quoting passages<br/>labelled 'not AI reasoning']
  M -- ollama --> O[Local LLM: excerpts only,<br/>instruction-like lines stripped]
  O --> V{Validate: citations [S#] present & valid,<br/>no dose/diagnosis patterns, length}
  V -- pass --> AN[Answer labelled 'local AI model output']
  V -- fail / timeout --> FB[Deterministic fallback, labelled]
  P --> C[User clicks Confirm → separate API call<br/>re-authorized → task created]
```

* **Tool allowlist:** `TOOLS` in `agent.py`; `_call()` raises `ToolNotAllowed` for anything else
  (unit-tested). Only one tool is state-changing, and it only writes an inert proposal.
* **Separation of retrieval and action:** confirmation is a different endpoint
  (`POST /assistant/actions/{id}/confirm`) that re-checks the user and patient at execution time.
* **Audit:** each query records intent, mode, tool names and source count — never the question or answer.

## Modes

| Mode | Default | What the user sees |
|---|---|---|
| Deterministic (`mock`) | yes | Answers assembled by rules from records; label: *"Deterministic mode — … This is not AI reasoning."* |
| Local LLM (`ollama`) | no | Rephrased answer from quoted excerpts with `[S#]` citations; label: *"Local AI model output — generated from the cited excerpts only."* |
| Fallback | — | When the model is unreachable, times out or fails validation; label says so explicitly |

Mode is set by `HB_AI_MODE` and can be switched by an administrator (Administration → Demo configuration).

### Local LLM verification (actual results, 2026-10-15)

Tested against a real Ollama container (`docker compose --profile ollama`) with `qwen2.5:1.5b` on CPU:

* Reachability/model checks: OK.
* A grounded, cited answer passed validation: *"The cardiologist recommended a transthoracic echocardiogram within 6 weeks [S1]."*
* Several other answers were **rejected** because the small model omitted the mandatory `[S#]` citation, and one
  request exceeded the 45 s timeout on CPU; in all cases the assistant fell back to deterministic mode as designed.
* While testing, the dose-pattern guard was found to also block quoted lab values ("151 mg/dL"); it was narrowed
  to exclude concentrations and a regression test was added.

Conclusion: the optional integration works end to end, but a 1.5B CPU model frequently fails the citation
contract. A larger model (e.g. the default `llama3.2:3b` or bigger) and/or a GPU is recommended; raise
`HB_OLLAMA_TIMEOUT_SECONDS` for CPU-only machines. Answer quality of local models has **not** been evaluated
beyond these checks.

## RAG pipeline (`services/rag.py`, `services/embeddings.py`)

1. **Ingestion** — text from PDF (pypdf), text files, or a readable rendering of FHIR resources.
2. **Normalization** — NFC, whitespace/control-character cleanup.
3. **Chunking** — paragraph/sentence-aware ~700 characters with 120 overlap; offsets kept for citations.
4. **Embeddings** — default `hash-v1`: deterministic feature hashing of words, word bigrams and character
   trigrams into 384 dimensions. It is local, reproducible and download-free, but **lexical, not semantic**.
   Optional `fastembed` (multilingual MiniLM, 384-d, ONNX, local) is supported via `HB_EMBEDDING_PROVIDER=fastembed`
   and falls back to `hash-v1` if unavailable (not installed in the default image).
5. **Index** — pgvector `vector(384)` with an HNSW cosine index; PostgreSQL `tsvector` (simple config) with GIN.
6. **Hybrid retrieval** — `0.65 × cosine + 0.35 × keyword rank` (OR-query of non-stopword tokens), threshold
   0.18; below threshold → explicit insufficient-evidence answer.
7. **Authorization first** — the caller passes `accessible_document_ids` from `AccessPolicy`; the SQL `WHERE`
   restricts to that set *and* the patient ID before ranking, so similarity can never surface unauthorized text.
   Chunks are also filtered to the active embedding provider and latest, non-deleted documents.

### Prompt-injection defences

* Retrieved text is treated as data: deterministic mode never interprets it.
* Chunks matching instruction-like patterns (EN/HE, e.g. "ignore previous instructions", "you are now") are
  flagged `suspicious` at index time; the UI shows a warning on those sources.
* Before LLM context, instruction-like lines are replaced with `[instruction-like text removed]`, the system
  prompt declares excerpts untrusted, and the output validator rejects uncited or prohibited content.
* Cross-patient leakage is structurally prevented by the authorization filter, not by the prompt.

### Retrieval evaluation (actual)

`backend/tests/test_rag_evaluation.py`, 10 labeled queries (EN + HE) on the synthetic corpus with `hash-v1`:
**hit@1 = 10/10, hit@3 = 10/10**. Caveats: tiny corpus (8 documents), queries share vocabulary with their
targets — this is a regression guard, not evidence of semantic retrieval quality. A second test proves that a
perfect lexical match is not returned when its document is outside the allowed set.

## Summary drafts

"Assemble draft from notes" concatenates the professionals' own consultation notes with participants and date.
It adds no clinical content, is labelled as an automatic draft, and must be saved, edited and approved like
any other version. Summaries become *approved* only when **every** participating professional approves.
