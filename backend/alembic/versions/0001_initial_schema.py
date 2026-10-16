"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2026-10-15 17:20:11.480825
"""
from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('app_settings',
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('audit_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('actor_role', sa.String(length=20), nullable=True),
    sa.Column('action', sa.String(length=60), nullable=False),
    sa.Column('resource_type', sa.String(length=40), nullable=True),
    sa.Column('resource_id', sa.String(length=64), nullable=True),
    sa.Column('patient_id', sa.Uuid(), nullable=True),
    sa.Column('outcome', sa.String(length=10), nullable=False),
    sa.Column('detail', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('prev_hash', sa.String(length=64), nullable=False),
    sa.Column('hash', sa.String(length=64), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_events_action'), 'audit_events', ['action'], unique=False)
    op.create_index(op.f('ix_audit_events_actor_id'), 'audit_events', ['actor_id'], unique=False)
    op.create_index(op.f('ix_audit_events_patient_id'), 'audit_events', ['patient_id'], unique=False)
    op.create_index(op.f('ix_audit_events_ts'), 'audit_events', ['ts'], unique=False)
    op.create_table('job_runs',
    sa.Column('job_name', sa.String(length=60), nullable=False),
    sa.Column('last_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_status', sa.String(length=20), nullable=True),
    sa.Column('last_error', sa.String(length=500), nullable=True),
    sa.Column('runs', sa.Integer(), nullable=False),
    sa.Column('items_processed', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('job_name')
    )
    op.create_table('organizations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('name_he', sa.String(length=200), nullable=True),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('country', sa.String(length=2), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('synthetic', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('locale', sa.String(length=5), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('country', sa.String(length=2), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('failed_logins', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)
    op.create_table('assistant_actions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('action_type', sa.String(length=40), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('auth_sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('csrf_token', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('user_agent', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token_hash')
    )
    op.create_index(op.f('ix_auth_sessions_user_id'), 'auth_sessions', ['user_id'], unique=False)
    op.create_table('consultations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=True),
    sa.Column('scheduled_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('duration_minutes', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('room_name', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reminder_sent', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('room_name')
    )
    op.create_index(op.f('ix_consultations_patient_id'), 'consultations', ['patient_id'], unique=False)
    op.create_index(op.f('ix_consultations_scheduled_start'), 'consultations', ['scheduled_start'], unique=False)
    op.create_table('documents',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('uploaded_by', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('storage_key', sa.String(length=100), nullable=False),
    sa.Column('encrypted', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('status_detail', sa.Text(), nullable=True),
    sa.Column('extracted_text', sa.Text(), nullable=True),
    sa.Column('text_sha256', sa.String(length=64), nullable=True),
    sa.Column('document_date', sa.Date(), nullable=True),
    sa.Column('author_name', sa.String(length=200), nullable=True),
    sa.Column('source_detected', sa.String(length=300), nullable=True),
    sa.Column('language', sa.String(length=5), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('lineage_id', sa.Uuid(), nullable=False),
    sa.Column('is_latest', sa.Boolean(), nullable=False),
    sa.Column('duplicate_of_id', sa.Uuid(), nullable=True),
    sa.Column('import_report', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['duplicate_of_id'], ['documents.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_documents_category'), 'documents', ['category'], unique=False)
    op.create_index(op.f('ix_documents_lineage_id'), 'documents', ['lineage_id'], unique=False)
    op.create_index(op.f('ix_documents_patient_id'), 'documents', ['patient_id'], unique=False)
    op.create_index(op.f('ix_documents_sha256'), 'documents', ['sha256'], unique=False)
    op.create_index(op.f('ix_documents_status'), 'documents', ['status'], unique=False)
    op.create_table('notification_preferences',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'kind')
    )
    op.create_table('notifications',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('link', sa.String(length=300), nullable=True),
    sa.Column('dedupe_key', sa.String(length=200), nullable=True),
    sa.Column('channel', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'dedupe_key', name='uq_notification_dedupe')
    )
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_table('patient_profiles',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('date_of_birth', sa.Date(), nullable=True),
    sa.Column('primary_organization_id', sa.Uuid(), nullable=True),
    sa.Column('show_access_alerts', sa.Boolean(), nullable=False),
    sa.Column('default_share_days', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['primary_organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('professional_profiles',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('specialty', sa.String(length=100), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=True),
    sa.Column('license_number', sa.String(length=50), nullable=False),
    sa.Column('verification_status', sa.String(length=20), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('consent_grants',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('grantee_id', sa.Uuid(), nullable=False),
    sa.Column('categories', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('include_journey', sa.Boolean(), nullable=False),
    sa.Column('include_care_gaps', sa.Boolean(), nullable=False),
    sa.Column('purpose', sa.String(length=300), nullable=True),
    sa.Column('consultation_id', sa.Uuid(), nullable=True),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expiry_notified', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['consultation_id'], ['consultations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['grantee_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_consent_grants_grantee_id'), 'consent_grants', ['grantee_id'], unique=False)
    op.create_index(op.f('ix_consent_grants_patient_id'), 'consent_grants', ['patient_id'], unique=False)
    op.create_table('consultation_documents',
    sa.Column('consultation_id', sa.Uuid(), nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['consultation_id'], ['consultations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('consultation_id', 'document_id')
    )
    op.create_table('consultation_notes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('consultation_id', sa.Uuid(), nullable=False),
    sa.Column('author_id', sa.Uuid(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['consultation_id'], ['consultations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_consultation_notes_consultation_id'), 'consultation_notes', ['consultation_id'], unique=False)
    op.create_table('consultation_participants',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('consultation_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('meeting_role', sa.String(length=20), nullable=False),
    sa.Column('invite_status', sa.String(length=20), nullable=False),
    sa.Column('last_token_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['consultation_id'], ['consultations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('consultation_id', 'user_id', name='uq_participant')
    )
    op.create_index(op.f('ix_consultation_participants_consultation_id'), 'consultation_participants', ['consultation_id'], unique=False)
    op.create_index(op.f('ix_consultation_participants_user_id'), 'consultation_participants', ['user_id'], unique=False)
    op.create_table('consultation_summaries',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('consultation_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('discussion', sa.Text(), nullable=False),
    sa.Column('observations', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('proposed_followups', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('referenced_document_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('ai_generated_draft', sa.Boolean(), nullable=False),
    sa.Column('author_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('patient_acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('document_id', sa.Uuid(), nullable=True),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['consultation_id'], ['consultations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_consultation_summaries_consultation_id'), 'consultation_summaries', ['consultation_id'], unique=False)
    op.create_table('document_chunks',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('char_start', sa.Integer(), nullable=False),
    sa.Column('char_end', sa.Integer(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.Column('embedding_provider', sa.String(length=80), nullable=False),
    sa.Column('suspicious', sa.Boolean(), nullable=False),
    sa.Column('tsv', postgresql.TSVECTOR(), sa.Computed("to_tsvector('simple', text)", persisted=True), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_chunks_embedding', 'document_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_chunks_tsv', 'document_chunks', ['tsv'], unique=False, postgresql_using='gin')
    op.create_index(op.f('ix_document_chunks_document_id'), 'document_chunks', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_chunks_patient_id'), 'document_chunks', ['patient_id'], unique=False)
    op.create_table('journey_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('event_type', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('organization_id', sa.Uuid(), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('verification_status', sa.String(length=30), nullable=False),
    sa.Column('provenance', sa.String(length=30), nullable=False),
    sa.Column('provenance_detail', sa.String(length=500), nullable=True),
    sa.Column('consultation_id', sa.Uuid(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['consultation_id'], ['consultations.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_journey_events_event_type'), 'journey_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_journey_events_occurred_at'), 'journey_events', ['occurred_at'], unique=False)
    op.create_index(op.f('ix_journey_events_patient_id'), 'journey_events', ['patient_id'], unique=False)
    op.create_table('event_documents',
    sa.Column('event_id', sa.Uuid(), nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['event_id'], ['journey_events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('event_id', 'document_id')
    )
    op.create_table('grant_documents',
    sa.Column('grant_id', sa.Uuid(), nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['grant_id'], ['consent_grants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('grant_id', 'document_id')
    )
    op.create_table('handoffs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('summary_id', sa.Uuid(), nullable=False),
    sa.Column('from_user_id', sa.Uuid(), nullable=False),
    sa.Column('to_user_id', sa.Uuid(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('grant_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('shared_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['from_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['grant_id'], ['consent_grants.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['summary_id'], ['consultation_summaries.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['to_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_handoffs_patient_id'), 'handoffs', ['patient_id'], unique=False)
    op.create_index(op.f('ix_handoffs_to_user_id'), 'handoffs', ['to_user_id'], unique=False)
    op.create_table('recommendations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=True),
    sa.Column('event_id', sa.Uuid(), nullable=True),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('original_text', sa.Text(), nullable=True),
    sa.Column('passage', sa.Text(), nullable=True),
    sa.Column('char_start', sa.Integer(), nullable=True),
    sa.Column('char_end', sa.Integer(), nullable=True),
    sa.Column('timeframe_text', sa.String(length=200), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('target', sa.String(length=200), nullable=True),
    sa.Column('review_status', sa.String(length=20), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('proposed_by', sa.Uuid(), nullable=True),
    sa.Column('documented_at', sa.Date(), nullable=True),
    sa.Column('reviewed_by', sa.Uuid(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['event_id'], ['journey_events.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['proposed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recommendations_document_id'), 'recommendations', ['document_id'], unique=False)
    op.create_index(op.f('ix_recommendations_patient_id'), 'recommendations', ['patient_id'], unique=False)
    op.create_table('summary_approvals',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('summary_id', sa.Uuid(), nullable=False),
    sa.Column('professional_id', sa.Uuid(), nullable=False),
    sa.Column('decision', sa.String(length=20), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['professional_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['summary_id'], ['consultation_summaries.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('summary_id', 'professional_id', name='uq_summary_approval')
    )
    op.create_index(op.f('ix_summary_approvals_summary_id'), 'summary_approvals', ['summary_id'], unique=False)
    op.create_table('care_gaps',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('rule_id', sa.String(length=20), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('computed_status', sa.String(length=30), nullable=False),
    sa.Column('review_status', sa.String(length=30), nullable=True),
    sa.Column('supporting_evidence', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('missing_evidence', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('document_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('relevant_dates', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('suggested_clarification', sa.Text(), nullable=True),
    sa.Column('params', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('recommendation_id', sa.Uuid(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('review_note', sa.Text(), nullable=True),
    sa.Column('reviewed_by', sa.Uuid(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_detected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_evaluated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recommendation_id'], ['recommendations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('patient_id', 'fingerprint', name='uq_gap_fingerprint')
    )
    op.create_index(op.f('ix_care_gaps_patient_id'), 'care_gaps', ['patient_id'], unique=False)
    op.create_table('followup_tasks',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('recommendation_id', sa.Uuid(), nullable=True),
    sa.Column('care_gap_id', sa.Uuid(), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('owner_id', sa.Uuid(), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('due_date_source', sa.String(length=20), nullable=True),
    sa.Column('status', sa.String(length=25), nullable=False),
    sa.Column('evidence_document_id', sa.Uuid(), nullable=True),
    sa.Column('completion_note', sa.Text(), nullable=True),
    sa.Column('completed_by', sa.Uuid(), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verified_by', sa.Uuid(), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reminder_days_before', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['care_gap_id'], ['care_gaps.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['completed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['evidence_document_id'], ['documents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recommendation_id'], ['recommendations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['verified_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_followup_tasks_patient_id'), 'followup_tasks', ['patient_id'], unique=False)
    op.create_index(op.f('ix_followup_tasks_status'), 'followup_tasks', ['status'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_followup_tasks_status'), table_name='followup_tasks')
    op.drop_index(op.f('ix_followup_tasks_patient_id'), table_name='followup_tasks')
    op.drop_table('followup_tasks')
    op.drop_index(op.f('ix_care_gaps_patient_id'), table_name='care_gaps')
    op.drop_table('care_gaps')
    op.drop_index(op.f('ix_summary_approvals_summary_id'), table_name='summary_approvals')
    op.drop_table('summary_approvals')
    op.drop_index(op.f('ix_recommendations_patient_id'), table_name='recommendations')
    op.drop_index(op.f('ix_recommendations_document_id'), table_name='recommendations')
    op.drop_table('recommendations')
    op.drop_index(op.f('ix_handoffs_to_user_id'), table_name='handoffs')
    op.drop_index(op.f('ix_handoffs_patient_id'), table_name='handoffs')
    op.drop_table('handoffs')
    op.drop_table('grant_documents')
    op.drop_table('event_documents')
    op.drop_index(op.f('ix_journey_events_patient_id'), table_name='journey_events')
    op.drop_index(op.f('ix_journey_events_occurred_at'), table_name='journey_events')
    op.drop_index(op.f('ix_journey_events_event_type'), table_name='journey_events')
    op.drop_table('journey_events')
    op.drop_index(op.f('ix_document_chunks_patient_id'), table_name='document_chunks')
    op.drop_index(op.f('ix_document_chunks_document_id'), table_name='document_chunks')
    op.drop_index('ix_chunks_tsv', table_name='document_chunks', postgresql_using='gin')
    op.drop_index('ix_chunks_embedding', table_name='document_chunks', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('document_chunks')
    op.drop_index(op.f('ix_consultation_summaries_consultation_id'), table_name='consultation_summaries')
    op.drop_table('consultation_summaries')
    op.drop_index(op.f('ix_consultation_participants_user_id'), table_name='consultation_participants')
    op.drop_index(op.f('ix_consultation_participants_consultation_id'), table_name='consultation_participants')
    op.drop_table('consultation_participants')
    op.drop_index(op.f('ix_consultation_notes_consultation_id'), table_name='consultation_notes')
    op.drop_table('consultation_notes')
    op.drop_table('consultation_documents')
    op.drop_index(op.f('ix_consent_grants_patient_id'), table_name='consent_grants')
    op.drop_index(op.f('ix_consent_grants_grantee_id'), table_name='consent_grants')
    op.drop_table('consent_grants')
    op.drop_table('professional_profiles')
    op.drop_table('patient_profiles')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_created_at'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_table('notification_preferences')
    op.drop_index(op.f('ix_documents_status'), table_name='documents')
    op.drop_index(op.f('ix_documents_sha256'), table_name='documents')
    op.drop_index(op.f('ix_documents_patient_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_lineage_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_category'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_consultations_scheduled_start'), table_name='consultations')
    op.drop_index(op.f('ix_consultations_patient_id'), table_name='consultations')
    op.drop_table('consultations')
    op.drop_index(op.f('ix_auth_sessions_user_id'), table_name='auth_sessions')
    op.drop_table('auth_sessions')
    op.drop_table('assistant_actions')
    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('organizations')
    op.drop_table('job_runs')
    op.drop_index(op.f('ix_audit_events_ts'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_patient_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_actor_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_action'), table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_table('app_settings')
    # ### end Alembic commands ###
