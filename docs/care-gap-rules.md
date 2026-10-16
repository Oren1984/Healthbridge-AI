# Care Gap Intelligence — rules

Source: `backend/app/services/care_gaps.py`. Tests: `backend/tests/test_unit_care_gaps.py` (pure, no DB)
and `test_api_care.py` / `test_api_consultations.py` (integrated).

## Principles

* **Deterministic.** `evaluate_snapshot(snapshot, as_of)` is a pure function. The same records and date
  always produce the same findings, fingerprints and wording (`GET /patients/{pid}/care-gaps/replay?as_of=`).
* **Absence of evidence ≠ evidence of absence.** If no document shows that something happened, the status is
  **Unknown**, and the text says explicitly that it may have happened elsewhere.
* **Administrative only.** No urgency scoring, no diagnosis, no treatment advice. Suggestions are questions to
  ask or documents to request (asserted by `test_suggestions_are_administrative_never_clinical`).
* **Evidence can close; claims cannot.** A task marked done without a document stays Unknown. Only a document
  (or a documented later event) yields **Completed & verified**.
* **Humans keep the last word.** Authorized users can mark *Not applicable* (reason required) or
  *Requires clarification*; these persist across re-evaluation. Verified evidence clears a clarification flag;
  a dismissal stays until reopened.

## Statuses

| Status | Meaning |
|---|---|
| `completed_verified` | Supporting evidence exists (later report/result/letter, or task with an evidence document) |
| `open` | A follow-up task is documented as pending |
| `unknown` | Available records don't establish whether the action occurred |
| `requires_clarification` | Conflicting or insufficient information |
| `not_applicable` | An authorized user documented why tracking isn't needed |

## Rules

| ID | Trigger | Evidence that resolves it | Default status |
|---|---|---|---|
| CG-001 | Follow-up visit / imaging / other recommendation | Imaging: later `imaging_report` whose terms match the recommended test. Visit: later consultation event *with a document* at the recommending organization (or any HMO visit if the text says "family physician") | Unknown |
| CG-002 | Referral recommendation | Later specialist/international consultation event with linked documentation whose terms match the referral target (e.g. cardiology) | Unknown |
| CG-003 | Laboratory recommendation | Later `lab_result`/FHIR document covering **every** requested test; partial coverage lists the missing tests (e.g. "Laboratory result for: CBC") | Unknown |
| CG-004 | Consultation marked completed without an approved summary | Summary approved by all participating professionals | Open |
| CG-005 | Summary handed off but not acknowledged by the recipient | Recipient acknowledgment | Open |
| CG-006 | Event date and its document's date differ by > 2 days, or a document dated in the future | Human correction | Requires clarification |
| CG-007 | Two documents give the same follow-up (same kind and test) with different timeframes | Human clarification | Requires clarification |
| CG-008 | Imaging / lab / hospital / consultation event without the expected document type | Upload of the expected document | Unknown |
| CG-009 | A professional in an upcoming consultation cannot see documents behind open recommendations or on the agenda | Patient sharing decision | Unknown |

Follow-up tasks linked to a recommendation refine CG-001/2/3 when evidence is not already conclusive:
`open` → Open, `completed_reported` → Unknown (missing: a confirming document), `not_applicable` →
Not applicable, `completed_verified` with an evidence document → Completed & verified.

Rejected recommendations are ignored; recommendations still awaiting human review are evaluated but
labelled "extracted — awaiting human review".

## Matching vocabulary

Matching uses a deliberately small, explicit term vocabulary (`extraction.TERMS`: CBC, lipid panel, HbA1c,
TSH, troponin, echocardiogram, stress test, Holter, chest X-ray, ECG, cardiology, endocrinology) in English
and Hebrew. Targets are taken from the *action clause* of a recommendation, so "Exercise stress test after
the echocardiogram" targets the stress test only. Anything outside the vocabulary falls back to category and
date checks. This is an engineering choice for transparency and testability, not a clinical terminology
service (SNOMED CT / LOINC mapping would be required for real use).

## Golden-scenario findings (showcase data)

* CBC + lipid panel (HMO, 12 May) → **Unknown**: lipid result present, CBC missing.
* Lipid panel "in 6 months" (discharge) vs "in 3 months" (cardiology) → **Requires clarification** (CG-007).
* Referral letter dated 25 Jun attached to an event entered as 2 Jul → **Requires clarification** (CG-006).
* Chest X-ray event with no report → **Unknown** (CG-008).
* Referral to cardiology → **Completed & verified** by the Cedar Ridge letter.
* "Consider a second opinion…" → Unknown until the international consultation summary is approved, then
  **Completed & verified**; the echocardiogram stays Unknown because no imaging report exists.
