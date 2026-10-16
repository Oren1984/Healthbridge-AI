# Known limitations

**Clinical and regulatory**
* Synthetic-data demonstration only; not clinically validated; no compliance (HIPAA, GDPR, Israeli privacy law,
  medical-device) is claimed. See [privacy-regulatory.md](privacy-regulatory.md).
* Professional verification is a simulated administrator flag.

**Document intelligence**
* No OCR: scanned PDFs are marked *needs manual review*. PDF active-content detection is signature/structure based
  (no antivirus engine); object streams could hide markers from the byte scan.
* Extraction is rule-based on a small EN/HE vocabulary; recall on real-world letters is unknown. Day-first dates
  (`DD/MM/YYYY`) are assumed for slashes.
* Care-gap matching uses a small explicit term list, not SNOMED CT/LOINC; follow-up visit matching relies on
  organization identity or HMO visits.
* No document translation feature is implemented (original documents are always shown as-is).

**AI / RAG**
* Default embeddings are lexical (`hash-v1`), not semantic; cross-lingual retrieval does not work with it.
  The optional `fastembed` provider is supported in code but not installed in the default image and was not tested.
* The optional Ollama mode was verified with `qwen2.5:1.5b` on CPU: integration and fallback work, but the small model
  often omits citations (answers rejected) and can time out. Answer quality of local models was not evaluated.
* RAG evaluation uses a 10-query synthetic set — a regression guard, not a quality benchmark.

**Collaboration**
* Video verified with 3 participants on one machine (Chromium fake devices). Not tested across real networks,
  NATs or on Firefox/Safari; no TURN server is shipped. Local signalling is `ws://` (not TLS).
* In-meeting chat is ephemeral (LiveKit data channel) and not stored; there is no recording or transcription by design.
* Consultation join window is fixed (2 h before → 4 h after).

**Platform**
* In-process rate limiter and notification WebSocket polling — correct for a single backend instance only.
* Extracted text and RAG chunks are not encrypted at application level (files are). DB volume encryption is required for production.
* Revocation stops future access through HealthBridge only; documents already downloaded cannot be recalled.
  New versions of a shared document are not automatically shared (conservative by design).
* Audit log is tamper-evident (HMAC chain), not tamper-proof storage.
* Upstream images (pgvector, LiveKit) contain known CVEs in their base layers (see [security.md](security.md)).
* Accessibility: automated axe checks only; no manual screen-reader audit.
* Notifications are in-app only (no email/SMS) by design.
