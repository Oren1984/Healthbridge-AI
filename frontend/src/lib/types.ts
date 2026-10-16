export type Role = "patient" | "professional" | "admin";

export interface Org { id: string; name: string; name_he: string | null; kind: string; country: string; city: string | null; synthetic: boolean }
export interface UserBrief {
  id: string; full_name: string; role: Role; country: string; timezone: string;
  professional?: { specialty: string; verification_status: string; organization: Org | null; license_number?: string; verified_at?: string | null };
}
export interface Me extends UserBrief {
  email: string; locale: "en" | "he"; is_active: boolean; last_login_at: string | null;
  patient?: { date_of_birth: string | null; default_share_days: number; show_access_alerts: boolean };
}
export interface Doc {
  id: string; patient_id: string; title: string; category: string; original_filename: string; mime_type: string;
  size_bytes: number; status: string; status_detail: string | null; document_date: string | null; author_name: string | null;
  source_detected: string | null; language: string | null; organization: Org | null; version: number; lineage_id: string;
  is_latest: boolean; duplicate_of_id: string | null; encrypted: boolean; created_at: string; processed_at: string | null;
  uploaded_by: string; import_report: { imported: string[]; skipped: string[]; ignored_fields: string[]; errors: string[]; profiles_not_validated: string[] } | null;
}
export interface Rec {
  id: string; document_id: string | null; document_title: string | null; event_id: string | null; kind: string; text: string;
  original_text: string | null; passage: string | null; char_start: number | null; char_end: number | null;
  timeframe_text: string | null; due_date: string | null; targets: string[]; review_status: string; source: string;
  documented_at: string | null; reviewed_at: string | null; created_at: string;
}
export interface JourneyEvent {
  id: string; event_type: string; title: string; description: string | null; organization: Org | null; occurred_at: string;
  verification_status: string; provenance: string; provenance_detail: string | null; consultation_id: string | null;
  documents: { id: string; title: string; category: string }[]; hidden_documents: number; created_at: string;
  recommendations?: Rec[]; authorized_viewers?: (UserBrief & { via: string; expires_at: string })[];
}
export interface DocDetail extends Doc {
  extracted_text: string | null; versions: { id: string; version: number; created_at: string; is_latest: boolean }[];
  recommendations: Rec[]; events: JourneyEvent[]; can_edit: boolean;
}
export interface Evidence { type: string; id: string; label: string; detail?: string }
export interface Gap {
  id: string; rule_id: string; rule: string; title: string; description: string; status: string; computed_status: string;
  review_status: string | null; supporting_evidence: Evidence[]; missing_evidence: string[]; document_ids: string[];
  relevant_dates: Record<string, string | null>; suggested_clarification: string | null; params: Record<string, any>;
  recommendation_id: string | null; active: boolean; review_note: string | null; reviewed_at: string | null;
  first_detected_at: string; last_evaluated_at: string; redacted_for_viewer?: boolean;
}
export interface Task {
  id: string; patient_id: string; kind: string; title: string; description: string | null; recommendation_id: string | null;
  care_gap_id: string | null; owner_id: string | null; due_date: string | null; due_date_source: string | null; status: string;
  evidence_document_id: string | null; completion_note: string | null; completed_at: string | null; verified_at: string | null;
  reminder_days_before: number | null; created_at: string; updated_at: string;
}
export interface Grant {
  id: string; patient_id: string; grantee: UserBrief; documents: { id: string; title: string; category: string }[];
  categories: string[]; include_journey: boolean; include_care_gaps: boolean; purpose: string | null;
  consultation_id: string | null; starts_at: string; expires_at: string; revoked_at: string | null; created_at: string;
  state: "active" | "expired" | "revoked" | "scheduled";
}
export interface Participant { user: UserBrief; meeting_role: string; invite_status: string; joined_at: string | null; left_at: string | null }
export interface Consultation {
  id: string; patient_id: string; title: string; purpose: string | null; scheduled_start: string; duration_minutes: number;
  status: string; created_at: string; completed_at: string | null; recording: string; participants: Participant[];
  documents: { id: string; title: string; category: string; accessible?: boolean }[]; my_invite_status: string | null;
  notes?: { id: string; author: UserBrief; content: string; created_at: string }[]; can_manage?: boolean;
  is_professional_participant?: boolean; join_window?: { opens: string; closes: string };
}
export interface Summary {
  id: string; consultation_id: string; version: number; status: string; discussion: string;
  observations: { author_id: string; author_name: string; text: string }[];
  proposed_followups: { title: string; description?: string | null }[]; referenced_document_ids: string[];
  ai_generated_draft: boolean; author: UserBrief; created_at: string; approved_at: string | null;
  patient_acknowledged_at: string | null; document_id: string | null;
  approvals: { professional: UserBrief; decision: string; comment: string | null; at: string }[]; awaiting_approval_from: string[];
}
export interface Handoff {
  id: string; patient_id: string; summary_id: string; consultation: { id: string; title: string } | null;
  summary_document_id: string | null; from: UserBrief; to: UserBrief; note: string | null; status: string;
  created_at: string; shared_at: string | null; acknowledged_at: string | null;
}
export interface Notification { id: string; kind: string; title: string; body: string | null; link: string | null; channel: string; created_at: string; read_at: string | null }
export interface AuditEntry { id: number; ts: string; action: string; outcome: string; resource_type: string | null; resource_id: string | null; actor: { full_name: string; role?: string; country?: string } | null; detail: Record<string, any> }
export interface AgentSource { ref: string; document_id: string; title: string; date: string | null; excerpt: string; score: number; suspicious: boolean }
export interface AgentReply {
  answer: string; intent: string; mode: string; label: string; tools_used: string[]; sources: AgentSource[];
  items: any[]; insufficient_evidence: boolean; pending_action: { id: string; type: string; payload: { title: string } } | null; warnings: string[];
}
