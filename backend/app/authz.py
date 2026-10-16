"""Server-side authorization policy — the single source of truth for clinical data access.

Rules
- A patient can access only their own records.
- A professional can access a patient's documents only through an *active* consent grant that
  names the document or its category, plus consultation summaries of consultations they took
  part in. Journey/care-gap views require the corresponding grant flags.
- Meeting membership alone never grants record access.
- Administrators have no clinical access.
Objects that are not visible are reported as 404 to avoid confirming their existence (BOLA).
"""
import uuid

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app import audit
from app.models import (
    ConsentGrant,
    Consultation,
    ConsultationParticipant,
    ConsultationSummary,
    Document,
    GrantDocument,
    User,
    utcnow,
)


class AccessPolicy:
    def __init__(self, db: Session, user: User) -> None:
        self.db = db
        self.user = user

    # ------------------------------------------------------------ helpers
    def _active_grant_filter(self, patient_id: uuid.UUID):
        now = utcnow()
        return and_(
            ConsentGrant.patient_id == patient_id,
            ConsentGrant.grantee_id == self.user.id,
            ConsentGrant.revoked_at.is_(None),
            ConsentGrant.starts_at <= now,
            ConsentGrant.expires_at > now,
        )

    def active_grants(self, patient_id: uuid.UUID) -> list[ConsentGrant]:
        if self.user.role != "professional":
            return []
        return list(self.db.execute(select(ConsentGrant).where(self._active_grant_filter(patient_id))).scalars())

    def deny(self, action: str, resource_type: str, resource_id, patient_id=None) -> HTTPException:
        audit.record_denied(self.db, action, self.user, resource_type=resource_type,
                            resource_id=resource_id, patient_id=patient_id)
        return HTTPException(404, "Not found")

    # ------------------------------------------------------------ patient-level
    def is_self(self, patient_id: uuid.UUID) -> bool:
        return self.user.role == "patient" and self.user.id == patient_id

    def can_view_patient_section(self, patient_id: uuid.UUID, section: str) -> bool:
        """section: documents | journey | care_gaps | tasks"""
        if self.is_self(patient_id):
            return True
        if self.user.role != "professional":
            return False
        grants = self.active_grants(patient_id)
        if section == "documents":
            return bool(grants)
        if section in ("journey", "tasks"):
            return any(g.include_journey for g in grants)
        if section == "care_gaps":
            return any(g.include_care_gaps for g in grants)
        return False

    def require_section(self, patient_id: uuid.UUID, section: str) -> None:
        if not self.can_view_patient_section(patient_id, section):
            raise self.deny(f"{section}.view", "patient", patient_id, patient_id)

    def require_self(self, patient_id: uuid.UUID, action: str) -> None:
        if not self.is_self(patient_id):
            raise self.deny(action, "patient", patient_id, patient_id)

    # ------------------------------------------------------------ documents
    def accessible_document_ids(self, patient_id: uuid.UUID) -> set[uuid.UUID]:
        """IDs of non-deleted documents this user may read for the patient.

        Used before retrieval so unauthorized content never reaches ranking or model context.
        """
        base = select(Document.id).where(Document.patient_id == patient_id, Document.deleted_at.is_(None))
        if self.is_self(patient_id):
            return set(self.db.execute(base).scalars())
        if self.user.role != "professional":
            return set()
        grants = self.active_grants(patient_id)
        ids: set[uuid.UUID] = set()
        categories: set[str] = set()
        for g in grants:
            categories.update(g.categories or [])
        grant_ids = [g.id for g in grants]
        conds = []
        if grant_ids:
            conds.append(Document.id.in_(select(GrantDocument.document_id).where(GrantDocument.grant_id.in_(grant_ids))))
        if categories:
            conds.append(Document.category.in_(categories))
        # Summaries of consultations this professional took part in.
        conds.append(
            Document.id.in_(
                select(ConsultationSummary.document_id)
                .join(Consultation, Consultation.id == ConsultationSummary.consultation_id)
                .join(ConsultationParticipant, ConsultationParticipant.consultation_id == Consultation.id)
                .where(ConsultationParticipant.user_id == self.user.id, Consultation.patient_id == patient_id,
                       ConsultationSummary.document_id.is_not(None))
            )
        )
        ids.update(self.db.execute(base.where(or_(*conds))).scalars())
        return ids

    def get_document(self, document_id: uuid.UUID, action: str = "document.view") -> Document:
        doc = self.db.get(Document, document_id)
        if not doc or doc.deleted_at is not None:
            raise HTTPException(404, "Not found")
        if self.is_self(doc.patient_id):
            return doc
        if self.user.role == "professional" and doc.id in self.accessible_document_ids(doc.patient_id):
            return doc
        raise self.deny(action, "document", document_id, doc.patient_id)

    # ------------------------------------------------------------ consultations
    def get_consultation(self, consultation_id: uuid.UUID, action: str = "consultation.view") -> Consultation:
        c = self.db.get(Consultation, consultation_id)
        if not c:
            raise HTTPException(404, "Not found")
        if self.user.role in ("patient", "professional") and any(
            p.user_id == self.user.id and p.invite_status != "declined" for p in c.participants
        ):
            return c
        raise self.deny(action, "consultation", consultation_id, c.patient_id)

    def is_professional_participant(self, c: Consultation) -> bool:
        return self.user.role == "professional" and any(
            p.user_id == self.user.id and p.meeting_role == "professional" and p.invite_status != "declined"
            for p in c.participants
        )

    # ------------------------------------------------------------ patients a professional can see
    def accessible_patient_ids(self) -> set[uuid.UUID]:
        if self.user.role == "patient":
            return {self.user.id}
        if self.user.role != "professional":
            return set()
        now = utcnow()
        q = select(ConsentGrant.patient_id).where(
            ConsentGrant.grantee_id == self.user.id, ConsentGrant.revoked_at.is_(None),
            ConsentGrant.starts_at <= now, ConsentGrant.expires_at > now,
        )
        return set(self.db.execute(q).scalars())
