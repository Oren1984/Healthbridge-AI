"""HL7 FHIR R4-compatible import/export for a deliberately small resource subset.

This is *not* a conformant FHIR server and does not validate against profiles or terminology
bindings. It checks the R4 base-resource cardinality for the fields it uses, maps supported
content into the internal model, and reports everything it ignored.
"""
import base64
import binascii
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, ValidationError

SUPPORTED_IMPORT_TYPES = {"Bundle", "Encounter", "Observation", "DiagnosticReport", "ServiceRequest",
                          "DocumentReference", "CarePlan", "Patient"}


class _R(BaseModel):
    model_config = ConfigDict(extra="allow")
    resourceType: str
    id: str | None = None


class Coding(BaseModel):
    model_config = ConfigDict(extra="allow")
    system: str | None = None
    code: str | None = None
    display: str | None = None


class CodeableConcept(BaseModel):
    model_config = ConfigDict(extra="allow")
    coding: list[Coding] = []
    text: str | None = None

    def label(self) -> str:
        if self.text:
            return self.text
        for c in self.coding:
            if c.display or c.code:
                return c.display or c.code or ""
        return ""


class Reference(BaseModel):
    model_config = ConfigDict(extra="allow")
    reference: str | None = None
    display: str | None = None


class Period(BaseModel):
    model_config = ConfigDict(extra="allow")
    start: str | None = None
    end: str | None = None


class Quantity(BaseModel):
    model_config = ConfigDict(extra="allow")
    value: float | None = None
    unit: str | None = None


class Encounter(_R):
    status: str
    class_: Coding | None = None
    type: list[CodeableConcept] = []
    period: Period | None = None
    serviceProvider: Reference | None = None
    reasonCode: list[CodeableConcept] = []


class Observation(_R):
    status: str
    code: CodeableConcept
    category: list[CodeableConcept] = []
    effectiveDateTime: str | None = None
    valueQuantity: Quantity | None = None
    valueString: str | None = None
    interpretation: list[CodeableConcept] = []
    performer: list[Reference] = []


class DiagnosticReport(_R):
    status: str
    code: CodeableConcept
    category: list[CodeableConcept] = []
    effectiveDateTime: str | None = None
    issued: str | None = None
    conclusion: str | None = None
    performer: list[Reference] = []


class ServiceRequest(_R):
    status: str
    intent: str
    subject: Reference
    code: CodeableConcept | None = None
    category: list[CodeableConcept] = []
    authoredOn: str | None = None
    occurrenceDateTime: str | None = None
    note: list[dict] = []
    requester: Reference | None = None


class Attachment(BaseModel):
    model_config = ConfigDict(extra="allow")
    contentType: str | None = None
    data: str | None = None
    title: str | None = None


class DocumentReferenceContent(BaseModel):
    model_config = ConfigDict(extra="allow")
    attachment: Attachment


class DocumentReference(_R):
    status: str
    content: list[DocumentReferenceContent]
    type: CodeableConcept | None = None
    date: str | None = None
    description: str | None = None


class CarePlanActivityDetail(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str | None = None
    description: str | None = None
    code: CodeableConcept | None = None


class CarePlanActivity(BaseModel):
    model_config = ConfigDict(extra="allow")
    detail: CarePlanActivityDetail | None = None


class CarePlan(_R):
    status: str
    intent: str
    subject: Reference
    activity: list[CarePlanActivity] = []
    created: str | None = None
    title: str | None = None


_MODELS = {"Encounter": Encounter, "Observation": Observation, "DiagnosticReport": DiagnosticReport,
           "ServiceRequest": ServiceRequest, "DocumentReference": DocumentReference, "CarePlan": CarePlan}
# Top-level fields each mapping actually uses; anything else is reported as ignored.
_USED_FIELDS = {
    "Encounter": {"resourceType", "id", "status", "class", "type", "period", "serviceProvider", "reasonCode"},
    "Observation": {"resourceType", "id", "status", "code", "category", "effectiveDateTime", "valueQuantity",
                    "valueString", "interpretation", "performer", "subject"},
    "DiagnosticReport": {"resourceType", "id", "status", "code", "category", "effectiveDateTime", "issued",
                         "conclusion", "performer", "subject"},
    "ServiceRequest": {"resourceType", "id", "status", "intent", "subject", "code", "category", "authoredOn",
                       "occurrenceDateTime", "note", "requester"},
    "DocumentReference": {"resourceType", "id", "status", "content", "type", "date", "description", "subject"},
    "CarePlan": {"resourceType", "id", "status", "intent", "subject", "activity", "created", "title"},
}


def parse_fhir_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if len(value) == 10:
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@dataclass
class MappedEvent:
    event_type: str
    title: str
    occurred_at: datetime
    description: str
    organization_name: str | None
    fhir_ref: str


@dataclass
class MappedRecommendation:
    kind: str
    text: str
    authored_on: date | None
    fhir_ref: str


@dataclass
class FhirImportResult:
    text: str = ""
    events: list[MappedEvent] = field(default_factory=list)
    recommendations: list[MappedRecommendation] = field(default_factory=list)
    report: dict = field(default_factory=lambda: {"imported": [], "skipped": [], "ignored_fields": [],
                                                   "errors": [], "profiles_not_validated": []})


def _iter_resources(obj: dict, report: dict):
    if obj.get("resourceType") == "Bundle":
        for i, entry in enumerate(obj.get("entry") or []):
            res = (entry or {}).get("resource")
            if isinstance(res, dict):
                yield f"entry[{i}]", res
            else:
                report["errors"].append(f"entry[{i}]: missing resource")
    else:
        yield "root", obj


def import_fhir(obj: dict) -> FhirImportResult:
    from app.services.extraction import classify_kind

    out = FhirImportResult()
    lines: list[str] = ["FHIR R4 import (synthetic data)", ""]
    for path, res in _iter_resources(obj, out.report):
        rtype = res.get("resourceType")
        ref = f"{rtype}/{res.get('id') or path}"
        if (res.get("meta") or {}).get("profile"):
            out.report["profiles_not_validated"].append(ref)
        if rtype == "Patient":
            out.report["skipped"].append(f"{ref}: Patient demographics are not imported (the uploading account is the subject)")
            continue
        model = _MODELS.get(rtype)
        if not model:
            out.report["skipped"].append(f"{ref}: unsupported resource type")
            continue
        payload = dict(res)
        if rtype == "Encounter" and "class" in payload:
            payload["class_"] = payload.pop("class")
        try:
            r = model.model_validate(payload)
        except ValidationError as exc:
            errs = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5])
            out.report["errors"].append(f"{ref}: {errs}")
            continue
        ignored = sorted(set(res) - _USED_FIELDS[rtype] - {"meta", "text"})
        if ignored:
            out.report["ignored_fields"].append(f"{ref}: {', '.join(ignored)}")
        out.report["imported"].append(ref)

        if isinstance(r, Encounter):
            when = parse_fhir_datetime(r.period.start if r.period else None)
            kind = r.type[0].label() if r.type else "Encounter"
            org = r.serviceProvider.display if r.serviceProvider else None
            cls = (r.class_.code or "").upper() if r.class_ else ""
            k = kind.lower()
            if cls in {"IMP", "EMER", "ACUTE"}:
                etype = "hospital_visit"
            elif "lab" in k:
                etype = "lab_test"
            elif "imaging" in k or "radiology" in k:
                etype = "imaging"
            elif "international" in k:
                etype = "international_consultation"
            elif "special" in k:
                etype = "specialist_consultation"
            else:
                etype = "other"  # never assume an encounter was a physician consultation
            reason = ", ".join(c.label() for c in r.reasonCode)
            lines.append(f"Encounter: {kind} at {org or 'unknown organization'} on {r.period.start if r.period else 'unknown date'}"
                         + (f" — reason: {reason}" if reason else ""))
            if when:
                out.events.append(MappedEvent(etype, kind, when, reason, org, ref))
        elif isinstance(r, Observation):
            val = (f"{r.valueQuantity.value:g} {r.valueQuantity.unit or ''}".strip() if r.valueQuantity and r.valueQuantity.value is not None
                   else r.valueString or "no value")
            interp = ", ".join(c.label() for c in r.interpretation)
            lines.append(f"Laboratory result: {r.code.label()}: {val}" + (f" ({interp})" if interp else "")
                         + (f" — collected {r.effectiveDateTime[:10]}" if r.effectiveDateTime else ""))
            when = parse_fhir_datetime(r.effectiveDateTime)
            if when:
                org = r.performer[0].display if r.performer else None
                out.events.append(MappedEvent("lab_test", f"Lab result: {r.code.label()}", when, "", org, ref))
        elif isinstance(r, DiagnosticReport):
            cats = " ".join(c.label() for c in r.category).upper()
            etype = "imaging" if any(k in cats for k in ("RAD", "IMG", "IMAGING")) else "lab_test"
            lines.append(f"Diagnostic report: {r.code.label()}" + (f" — conclusion: {r.conclusion}" if r.conclusion else ""))
            when = parse_fhir_datetime(r.effectiveDateTime or r.issued)
            if when:
                org = r.performer[0].display if r.performer else None
                out.events.append(MappedEvent(etype, r.code.label() or "Diagnostic report", when, r.conclusion or "", org, ref))
        elif isinstance(r, ServiceRequest):
            label = r.code.label() if r.code else "Service request"
            notes = " ".join(str(n.get("text", "")) for n in r.note if isinstance(n, dict))
            text = f"{label}" + (f" — {notes}" if notes else "")
            lines.append(f"Recommendation (ServiceRequest, status {r.status}): {text}")
            if r.status in {"active", "draft", "on-hold"}:
                authored = parse_fhir_datetime(r.authoredOn)
                out.recommendations.append(MappedRecommendation(classify_kind(text), text, authored.date() if authored else None, ref))
        elif isinstance(r, CarePlan):
            created = parse_fhir_datetime(r.created)
            for a in r.activity:
                d = a.detail
                if d and (d.description or d.code):
                    text = d.description or (d.code.label() if d.code else "")
                    lines.append(f"Care plan activity ({d.status or 'unknown status'}): {text}")
                    if (d.status or "") not in {"completed", "cancelled", "stopped"}:
                        out.recommendations.append(MappedRecommendation(classify_kind(text), text, created.date() if created else None, ref))
        elif isinstance(r, DocumentReference):
            for c in r.content:
                att = c.attachment
                if att.data and (att.contentType or "").startswith("text/plain"):
                    try:
                        lines.append(base64.b64decode(att.data, validate=True).decode("utf-8")[:20000])
                    except (binascii.Error, UnicodeDecodeError):
                        out.report["errors"].append(f"{ref}: attachment is not valid base64 UTF-8 text")
                elif att.data:
                    out.report["skipped"].append(f"{ref}: attachment type {att.contentType} not supported")
    out.text = "\n".join(lines)
    return out


# ------------------------------------------------------------------ export
_EVENT_CLASS = {"hospital_visit": "IMP", "discharge": "IMP"}
_TASK_STATUS = {"open": "requested", "completed_reported": "in-progress", "completed_verified": "completed",
                "not_applicable": "cancelled"}


def export_bundle(patient, events, documents, recommendations, tasks) -> dict:
    """Build a FHIR R4 collection Bundle of the patient's own records (metadata level)."""
    pref = f"Patient/{patient.id}"
    entries = [{"fullUrl": f"urn:uuid:{patient.id}", "resource": {
        "resourceType": "Patient", "id": str(patient.id), "name": [{"text": patient.full_name}],
        "meta": {"tag": [{"system": "urn:healthbridge", "code": "synthetic"}]}}}]
    for e in events:
        entries.append({"fullUrl": f"urn:uuid:{e.id}", "resource": {
            "resourceType": "Encounter", "id": str(e.id), "status": "finished",
            "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": _EVENT_CLASS.get(e.event_type, "AMB")},
            "type": [{"text": e.title}], "subject": {"reference": pref},
            "period": {"start": e.occurred_at.isoformat()},
            **({"serviceProvider": {"display": e.organization.name}} if e.organization else {})}})
    for d in documents:
        entries.append({"fullUrl": f"urn:uuid:{d.id}", "resource": {
            "resourceType": "DocumentReference", "id": str(d.id), "status": "current",
            "type": {"text": d.category}, "subject": {"reference": pref}, "description": d.title,
            **({"date": datetime.combine(d.document_date, datetime.min.time(), timezone.utc).isoformat()} if d.document_date else {}),
            "content": [{"attachment": {"contentType": d.mime_type, "title": d.original_filename,
                                        "url": f"/api/documents/{d.id}/download"}}]}})
    for r in recommendations:
        entries.append({"fullUrl": f"urn:uuid:{r.id}", "resource": {
            "resourceType": "ServiceRequest", "id": str(r.id), "status": "active", "intent": "plan",
            "subject": {"reference": pref}, "code": {"text": r.text},
            **({"authoredOn": r.documented_at.isoformat()} if r.documented_at else {})}})
    for t in tasks:
        entries.append({"fullUrl": f"urn:uuid:{t.id}", "resource": {
            "resourceType": "Task", "id": str(t.id), "status": _TASK_STATUS.get(t.status, "requested"),
            "intent": "plan", "description": t.title, "for": {"reference": pref},
            **({"focus": {"reference": f"ServiceRequest/{t.recommendation_id}"}} if t.recommendation_id else {}),
            **({"restriction": {"period": {"end": t.due_date.isoformat()}}} if t.due_date else {})}})
    return {"resourceType": "Bundle", "type": "collection",
            "timestamp": datetime.now(timezone.utc).isoformat(), "entry": entries}
