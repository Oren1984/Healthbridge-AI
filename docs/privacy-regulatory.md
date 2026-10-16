# Privacy and regulatory applicability

> **No compliance is claimed.** HealthBridge AI is a synthetic-data engineering demonstration. Implementing
> controls that resemble regulatory requirements does not make it compliant with HIPAA, GDPR, Israeli law or
> medical-device regulation. A real deployment requires qualified legal, privacy, clinical and regulatory review.
> This page is an engineering-oriented applicability analysis, not legal advice.

## Applicability matrix

Legend: **A** applicable to the design · **P** potentially applicable in a real deployment ·
**N/A** not applicable to the synthetic demo · **R** requires legal/clinical review.

| Framework / topic | Demo | Real deployment | Notes and implemented design controls |
|---|---|---|---|
| Israeli Protection of Privacy Law 5741-1981 | N/A (no real data) | **A / R** | Health data is sensitive. Design supports purpose limitation, access transparency, deletion of uploaded documents, export. Database registration/notification duties and controller obligations need legal review. |
| Protection of Privacy (Data Security) Regulations 2017 | N/A | **A / R** | Likely high security level for medical data. Implemented: access control, audit logging, encryption of files at rest, least privilege, security event review. Missing: formal security procedures, risk survey, periodic audits, incident procedures. |
| Amendment 13 (2024–2025) to the Privacy Protection Law | N/A | **R** | Expanded definitions, enforcement and data-subject rights; impact must be assessed by counsel. |
| Israeli Patients' Rights Law 1996 | N/A | **P / R** | Medical confidentiality and the right to medical information. HealthBridge is patient-held, not a provider record; obligations of providers remain with them. Revocation text states it cannot override provider record-keeping duties. |
| Cross-border transfer (Israel → US/UK physicians) | N/A | **A / R** | Israeli Transfer of Data Abroad Regulations 2001 and recipient-country law. Design: explicit, scoped, time-limited patient consent per professional; access is remote viewing via HealthBridge, but downloads are possible. Hosting location and transfer basis need review. |
| GDPR (EU/UK GDPR for the UK physician) | N/A | **P / R** | Applies if EU/UK establishments, monitoring, or EU/UK data subjects are involved. Health data = Art. 9 special category. Design supports Art. 15/20 (access, export), Art. 17 (document deletion), purpose limitation, data minimisation (sharing per document), Art. 32 controls. Missing: DPIA, records of processing, DPO, lawful-basis analysis, processor agreements. |
| HIPAA (US) | N/A | **P / R** | Applies only to covered entities and their business associates. A patient-directed app is often outside HIPAA, but a US physician's use may create obligations on their side; FTC Health Breach Notification Rule may apply to non-HIPAA health apps. Needs analysis. |
| Professional licensing / telemedicine | N/A | **R** | Cross-border consultation may constitute practice of medicine in the patient's jurisdiction. Verification here is **simulated** (admin flag); real deployment needs licence verification per country and clinical governance. |
| Medical device / SaMD (Israel AMAR, EU MDR, FDA) | N/A | **R** | Care gap detection and the assistant are designed as administrative tools (no diagnosis, urgency or treatment). Intended-use claims must stay administrative; any clinical claims could trigger SaMD classification (cf. IMDRF SaMD risk framework). |
| AI regulation (EU AI Act) | N/A | **P / R** | Optional LLM use is limited to rephrasing cited excerpts with labels and human oversight; classification depends on intended use. |
| Consent and lawful processing | **A** (simulated) | **A / R** | Granular consent grants with preview, expiry and revocation; no processing beyond user-initiated actions. |
| Data minimisation / purpose limitation | **A** | **A** | Share per document/category/section; professionals see nothing by default; admins see no clinical content; logs exclude content. |
| Retention and deletion | **A** (partial) | **A / R** | Patients can delete uploaded documents (file and search index removed; metadata tombstoned). Audit records are retained. No automated retention schedule — must be defined. |
| Access transparency | **A** | **A** | Patient-visible access history including denied attempts. |
| Incident response | — | **A / R** | Security events, denial logging and audit verification exist; no incident-response plan, breach-notification workflow or on-call. |

## Data flows (real-world equivalent)

1. Patient uploads documents → encrypted file storage + extracted text in the database (patient's own account).
2. Patient grants a professional access → professional views/downloads through HealthBridge; access logged.
3. Video consultation → media via self-hosted SFU; not recorded; chat not stored.
4. Summary approved → stored as a patient document; shared further only with patient approval (handoff).

## Synthetic-data statement

All people, organizations, documents and identifiers are fictional (`backend/app/seed_data.py`); emails use
the reserved `.test` TLD. There are no integrations with real HMOs, hospitals, laboratories or registries.
