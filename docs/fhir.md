# FHIR interoperability notes

HealthBridge is **FHIR R4-compatible for a small subset** of resources. It is not a FHIR server, does not
implement the REST API, and does not validate profiles, terminology bindings or invariants.
Code: `backend/app/services/fhir.py`. Tests: `test_unit_fhir_rag_agent.py::TestFhir`, `test_api_documents.py`.

## Import (upload a `.json` resource or Bundle)

| Resource | Required fields checked (R4 cardinality) | Mapped to |
|---|---|---|
| Encounter | `status`, `class` | Journey event (type from class/type text; ambulatory encounters are **not** assumed to be physician visits) |
| Observation | `status`, `code` | Text line in the document + `lab_test` event |
| DiagnosticReport | `status`, `code` | `lab_test` or `imaging` event (by category) + conclusion text |
| ServiceRequest | `status`, `intent`, `subject` | Recommendation (only `active`/`draft`/`on-hold`) |
| CarePlan | `status`, `intent`, `subject` | Recommendations from non-completed activities |
| DocumentReference | `status`, `content` | Plain-text base64 attachments appended to the document text |
| Patient | — | Skipped (the uploading account is the subject) |

Every FHIR document shows an **import report**: imported resources, skipped resources (unsupported types),
**ignored top-level fields** per resource, validation errors, and declared `meta.profile`s that were not validated.
Imported recommendations start as *awaiting review* like any extracted item.

## Export

`GET /api/patients/{pid}/fhir/export` (Privacy & audit → Export) returns a `collection` Bundle with Patient,
Encounter (journey events), DocumentReference (metadata + download URL), ServiceRequest (recommendations) and
Task (follow-ups). It is metadata-level and patient-initiated only.

## Gaps for real interoperability

Profile validation (e.g. IL Core, US Core, UK Core), terminology (LOINC, SNOMED CT, ICD-10), identifier
systems, provenance resources, SMART on FHIR authorization and bulk data are out of scope.
