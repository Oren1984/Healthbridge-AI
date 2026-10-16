"""Relational domain model for HealthBridge AI.

String-valued enums are used (validated in schemas/services) so migrations stay simple.
All primary keys exposed through the API are random UUIDs.
"""
import uuid
from datetime import date, datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

EMBEDDING_DIM = 384


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


Json = JSON().with_variant(JSONB(), "postgresql")


# ---------------------------------------------------------------- identity
class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), index=True)  # patient | professional | admin
    locale: Mapped[str] = mapped_column(String(5), default="en")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    country: Mapped[str] = mapped_column(String(2), default="IL")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    professional: Mapped["ProfessionalProfile | None"] = relationship(back_populates="user", uselist=False)
    patient: Mapped["PatientProfile | None"] = relationship(back_populates="user", uselist=False)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    name_he: Mapped[str | None] = mapped_column(String(200))
    # hmo | hospital | private_clinic | laboratory | imaging | international_clinic
    kind: Mapped[str] = mapped_column(String(30))
    country: Mapped[str] = mapped_column(String(2))
    city: Mapped[str | None] = mapped_column(String(100))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class PatientProfile(Base):
    __tablename__ = "patient_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    primary_organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    # Privacy preferences
    show_access_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    default_share_days: Mapped[int] = mapped_column(Integer, default=14)
    user: Mapped[User] = relationship(back_populates="patient")


class ProfessionalProfile(Base):
    __tablename__ = "professional_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    specialty: Mapped[str] = mapped_column(String(100))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    license_number: Mapped[str] = mapped_column(String(50))  # synthetic
    # simulated_verified | pending | rejected — SIMULATED, no real licensing check
    verification_status: Mapped[str] = mapped_column(String(20), default="pending")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship(back_populates="professional")
    organization: Mapped[Organization | None] = relationship()


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of opaque token
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(200))


# ---------------------------------------------------------------- documents & RAG
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    title: Mapped[str] = mapped_column(String(300))
    # consultation_note | lab_result | imaging_report | referral | discharge_summary |
    # consultation_summary | fhir_record | other
    category: Mapped[str] = mapped_column(String(40), default="other", index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(100))
    encrypted: Mapped[bool] = mapped_column(Boolean, default=True)
    # pending | processing | processed | needs_review | failed | unsupported
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    status_detail: Mapped[str | None] = mapped_column(Text)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    text_sha256: Mapped[str | None] = mapped_column(String(64))
    document_date: Mapped[date | None] = mapped_column(Date)
    author_name: Mapped[str | None] = mapped_column(String(200))
    source_detected: Mapped[str | None] = mapped_column(String(300))
    language: Mapped[str | None] = mapped_column(String(5))
    version: Mapped[int] = mapped_column(Integer, default=1)
    lineage_id: Mapped[uuid.UUID] = mapped_column(index=True)  # shared by all versions
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"))
    import_report: Mapped[dict | None] = mapped_column(Json)  # e.g. FHIR unsupported fields
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    organization: Mapped[Organization | None] = relationship()


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    embedding = mapped_column(Vector(EMBEDDING_DIM))
    embedding_provider: Mapped[str] = mapped_column(String(80))
    suspicious: Mapped[bool] = mapped_column(Boolean, default=False)  # instruction-like content
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True))

    __table_args__ = (
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


# ---------------------------------------------------------------- journey
class JourneyEvent(Base):
    __tablename__ = "journey_events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # hmo_consultation | specialist_consultation | hospital_visit | lab_test | imaging | referral |
    # discharge | follow_up_appointment | international_consultation | other
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # documented | patient_reported | professional_confirmed | unverified
    verification_status: Mapped[str] = mapped_column(String(30), default="unverified")
    # document | manual | fhir_import | consultation
    provenance: Mapped[str] = mapped_column(String(30))
    provenance_detail: Mapped[str | None] = mapped_column(String(500))
    consultation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("consultations.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    organization: Mapped[Organization | None] = relationship()
    documents: Mapped[list[Document]] = relationship(secondary="event_documents")


class EventDocument(Base):
    __tablename__ = "event_documents"
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("journey_events.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journey_events.id", ondelete="SET NULL"))
    # follow_up_visit | lab_test | imaging | referral | other
    kind: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text)
    original_text: Mapped[str | None] = mapped_column(Text)  # set when corrected
    passage: Mapped[str | None] = mapped_column(Text)  # exact source passage
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    timeframe_text: Mapped[str | None] = mapped_column(String(200))  # as documented, never computed
    due_date: Mapped[date | None] = mapped_column(Date)  # only when explicitly documented/entered
    target: Mapped[str | None] = mapped_column(String(200))  # test/specialty keywords
    # pending_review | confirmed | corrected | rejected
    review_status: Mapped[str] = mapped_column(String(20), default="pending_review")
    # extracted | manual | professional | fhir
    source: Mapped[str] = mapped_column(String(20))
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    documented_at: Mapped[date | None] = mapped_column(Date)  # date of source document
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document | None] = relationship()


class FollowUpTask(Base):
    __tablename__ = "followup_tasks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL"))
    care_gap_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("care_gaps.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), default="follow_up")  # follow_up | clarification
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    due_date_source: Mapped[str | None] = mapped_column(String(20))  # documented | user_entered
    # open | completed_reported | completed_verified | not_applicable
    status: Mapped[str] = mapped_column(String(25), default="open", index=True)
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    completion_note: Mapped[str | None] = mapped_column(Text)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_days_before: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CareGap(Base):
    __tablename__ = "care_gaps"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str] = mapped_column(String(20))
    fingerprint: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    # computed status from the rule:
    # completed_verified | open | unknown | requires_clarification | not_applicable
    computed_status: Mapped[str] = mapped_column(String(30))
    # human override (only not_applicable / requires_clarification); NULL = use computed
    review_status: Mapped[str | None] = mapped_column(String(30))
    supporting_evidence: Mapped[list] = mapped_column(Json, default=list)
    missing_evidence: Mapped[list] = mapped_column(Json, default=list)
    document_ids: Mapped[list] = mapped_column(Json, default=list)
    relevant_dates: Mapped[dict] = mapped_column(Json, default=dict)
    suggested_clarification: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(Json, default=dict)  # values for localized templates
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)  # rule still triggers
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("patient_id", "fingerprint", name="uq_gap_fingerprint"),)

    @property
    def status(self) -> str:
        return self.review_status or self.computed_status


# ---------------------------------------------------------------- consent
class ConsentGrant(Base):
    __tablename__ = "consent_grants"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    grantee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    categories: Mapped[list] = mapped_column(Json, default=list)  # document categories
    include_journey: Mapped[bool] = mapped_column(Boolean, default=False)
    include_care_gaps: Mapped[bool] = mapped_column(Boolean, default=False)
    purpose: Mapped[str | None] = mapped_column(String(300))
    consultation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("consultations.id", ondelete="SET NULL"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expiry_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    documents: Mapped[list[Document]] = relationship(secondary="grant_documents")
    grantee: Mapped[User] = relationship(foreign_keys=[grantee_id])

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return self.revoked_at is None and self.starts_at <= now < self.expires_at


class GrantDocument(Base):
    __tablename__ = "grant_documents"
    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consent_grants.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)


# ---------------------------------------------------------------- consultations
class Consultation(Base):
    __tablename__ = "consultations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    purpose: Mapped[str | None] = mapped_column(Text)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=45)
    # scheduled | in_progress | completed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    room_name: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    participants: Mapped[list["ConsultationParticipant"]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(secondary="consultation_documents")


class ConsultationParticipant(Base):
    __tablename__ = "consultation_participants"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    consultation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consultations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    meeting_role: Mapped[str] = mapped_column(String(20))  # patient | professional
    invite_status: Mapped[str] = mapped_column(String(20), default="invited")  # invited|accepted|declined
    last_token_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    consultation: Mapped[Consultation] = relationship(back_populates="participants")
    user: Mapped[User] = relationship()
    __table_args__ = (UniqueConstraint("consultation_id", "user_id", name="uq_participant"),)


class ConsultationDocument(Base):
    __tablename__ = "consultation_documents"
    consultation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consultations.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)


class ConsultationNote(Base):
    __tablename__ = "consultation_notes"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    consultation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consultations.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    author: Mapped[User] = relationship()


class ConsultationSummary(Base):
    __tablename__ = "consultation_summaries"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    consultation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consultations.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    # draft | pending_approval | approved | superseded
    status: Mapped[str] = mapped_column(String(20), default="draft")
    discussion: Mapped[str] = mapped_column(Text)
    observations: Mapped[list] = mapped_column(Json, default=list)  # [{author_id, author_name, text}]
    proposed_followups: Mapped[list] = mapped_column(Json, default=list)  # [{title, description}]
    referenced_document_ids: Mapped[list] = mapped_column(Json, default=list)
    ai_generated_draft: Mapped[bool] = mapped_column(Boolean, default=False)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    patient_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))

    author: Mapped[User] = relationship()
    approvals: Mapped[list["SummaryApproval"]] = relationship(cascade="all, delete-orphan")


class SummaryApproval(Base):
    __tablename__ = "summary_approvals"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    summary_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consultation_summaries.id", ondelete="CASCADE"), index=True)
    professional_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(20))  # approved | changes_requested
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    professional: Mapped[User] = relationship()
    __table_args__ = (UniqueConstraint("summary_id", "professional_id", name="uq_summary_approval"),)


class Handoff(Base):
    __tablename__ = "handoffs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    summary_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consultation_summaries.id", ondelete="CASCADE"))
    from_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    to_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    # pending_patient_approval | shared | declined
    status: Mapped[str] = mapped_column(String(30), default="pending_patient_approval")
    grant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("consent_grants.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------- notifications
class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # appointment_reminder | followup_pending | sharing_invitation | access_expiring |
    # consultation_update | document_processed | care_gap_clarification | handoff
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(20), default="in_app")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_notification_dedupe"),)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------- audit & ops
class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    actor_role: Mapped[str | None] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(60), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(40))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    patient_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    outcome: Mapped[str] = mapped_column(String(10))  # success | denied | error
    detail: Mapped[dict] = mapped_column(Json, default=dict)  # never PHI content
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class JobRun(Base):
    __tablename__ = "job_runs"
    job_name: Mapped[str] = mapped_column(String(60), primary_key=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))
    last_error: Mapped[str | None] = mapped_column(String(500))
    runs: Mapped[int] = mapped_column(Integer, default=0)
    items_processed: Mapped[int] = mapped_column(Integer, default=0)


class AssistantAction(Base):
    """A state change proposed by the assistant; inert until the user confirms it."""

    __tablename__ = "assistant_actions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    action_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(Json)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|confirmed|cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(Json)
