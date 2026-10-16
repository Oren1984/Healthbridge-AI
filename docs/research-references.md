# References

Standards and official sources consulted for design decisions. Which choices are research/standards-based
versus original engineering is noted per item. No research findings or validation results are claimed beyond
the tests in [testing.md](testing.md).

## Standards used directly

| Source | Used for |
|---|---|
| HL7 FHIR R4 (v4.0.1), <https://hl7.org/fhir/R4/> — resource definitions for Encounter, Observation, DiagnosticReport, ServiceRequest, CarePlan, DocumentReference, Bundle, Task | Field names and required cardinalities in `services/fhir.py`; export Bundle shape |
| W3C WCAG 2.2, <https://www.w3.org/TR/WCAG22/> | Accessibility targets; axe rule tags in E2E |
| OWASP Password Storage Cheat Sheet | Argon2id for password hashing |
| OWASP Cross-Site Request Forgery Prevention Cheat Sheet | Session-bound CSRF token in a custom header + SameSite cookies |
| OWASP API Security Top 10 (2023), API1: Broken Object Level Authorization | Central object-level policy, 404 for invisible objects, BOLA tests |
| OWASP Top 10 for LLM Applications (2025): LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM06 Excessive Agency | Authorization-before-retrieval, untrusted-content handling, tool allowlist, human confirmation for actions |
| Microsoft STRIDE threat modelling | Structure of [security.md](security.md) |
| RFC 9106 (Argon2) | Hashing parameters via `argon2-cffi` defaults |
| IMDRF, *Software as a Medical Device: Possible Framework for Risk Categorization* (2014) | Framing of the SaMD risk in the regulatory matrix |

## Legal frameworks referenced (not legal advice)

Israeli Protection of Privacy Law 5741-1981 and Protection of Privacy (Data Security) Regulations 2017;
Protection of Privacy (Transfer of Data to Databases Abroad) Regulations 2001; Israeli Patients' Rights Law
5756-1996; EU GDPR (Regulation 2016/679) incl. Art. 9, 15, 17, 20, 32; US HIPAA Privacy and Security Rules
(45 CFR Parts 160/164) and FTC Health Breach Notification Rule; EU MDR 2017/745; EU AI Act (Regulation 2024/1689).

## Technology documentation

LiveKit (self-hosted server, access tokens/grants, React components), pgvector (HNSW, cosine distance),
PostgreSQL full-text search (`tsvector`, `ts_rank_cd`), FastAPI, SQLAlchemy 2, Alembic, Playwright, axe-core.

## Original engineering choices (not derived from research)

The care-gap rule set and its five-status vocabulary; the "unknown ≠ not done" wording; the hashing embedder;
hybrid score weights (0.65/0.35) and the 0.18 threshold (calibrated on the synthetic corpus); the join window;
per-professional summary approval; the patient-approved handoff flow.
