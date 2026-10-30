// Types for the proposed Phase 1 API (`/api/v1`).
// Source of truth: docs/contracts/phase1-data-api-v1.md and
// docs/contracts/fixtures/phase1-api-examples-v1.json. Update both sides together.

export type StatusCode =
  "contacted" | "proposal_sent" | "awaiting_demo" | "follow_up_needed" | "closed";

export const STATUS_LABELS: Record<StatusCode, string> = {
  contacted: "Contacted",
  proposal_sent: "Proposal sent",
  awaiting_demo: "Awaiting demo",
  follow_up_needed: "Follow-up needed",
  closed: "Closed",
};

export type Channel = "gmail";

export type RecordType = "clinic" | "inquiry";

export type ClinicNameState = "confirmed" | "unknown";

/** One row in Due today, Needs clinic name or All leads. */
export interface LeadRow {
  lead_id: string;
  record_type: RecordType;
  clinic_id: string | null;
  /** Null when `clinic_name_state` is "unknown"; render "Clinic name unknown", never a blank cell. */
  clinic_name: string | null;
  clinic_name_state: ClinicNameState;
  contact_person?: string | null;
  contact_number?: string | null;
  email?: string | null;
  /** Null means unknown. */
  status_code: StatusCode | null;
  /** ISO date (YYYY-MM-DD) in the Asia/Manila business calendar. */
  next_action_date: string | null;
  next_action?: "request_clinic_name" | null;
  next_step?: string | null;
  /** Most recent linked interaction topic, a suggestion distinct from the operational next step. */
  latest_topic?: string | null;
  /** UTC instant; null when no linked interaction has a trustworthy event time. */
  last_contact_at?: string | null;
  channels?: Channel[];
  /** Required optimistic-concurrency token; send unchanged on every row edit. */
  version: number;
  /** True when a staff edit is visible before the next silver refresh. */
  pending_projection?: boolean;
  calling_notes?: string | null;
  person_spoken_to?: string | null;
  region?: string | null;
  province?: string | null;
  municipality?: string | null;
  address?: string | null;
}

/** Freshness metadata returned with lead lists. */
export interface Publication {
  /** Response time. */
  as_of: string;
  /** Last successful silver publication, not the latest connector poll. */
  published_at: string | null;
}

export interface LeadsPage extends Publication {
  items: LeadRow[];
  next_cursor: string | null;
}

export interface PipelineStatus extends Publication {
  last_run_status: "running" | "retrying" | "succeeded" | "failed" | null;
  is_stale: boolean;
  stale_after_minutes: number;
  pipelines: {
    pipeline: "gmail_ingest" | "silver_publish";
    last_run_status: PipelineStatus["last_run_status"];
    last_run_started_at: string | null;
    last_run_finished_at: string | null;
    last_succeeded_at: string | null;
    last_succeeded_data_as_of: string | null;
  }[];
}

export interface LeadsQuery {
  status?: StatusCode;
  q?: string;
  limit?: number;
  cursor?: string;
  next_action_date?: string;
}

export interface Interaction {
  raw_message_id: string;
  channel: Channel;
  direction: "inbound" | "outbound";
  event_at: string | null;
  excerpt?: string | null;
  /** Derived suggestion, not staff-confirmed. */
  topic: string | null;
  /** Derived suggestion, not staff-confirmed. */
  derived_status_code: StatusCode | null;
  source_account_id?: string;
  source_message_id?: string;
  source_thread_id?: string | null;
  staff_email?: string | null;
}

export interface HistoryPage {
  clinic_id: string | null;
  lead_id?: string;
  items: Interaction[];
  next_cursor: string | null;
}

export interface StaffUser {
  user_id: string;
  email: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: { field?: string; reason?: string; message?: string }[];
  };
}

// Legacy workbook import (FR-02, SNX-28): POST /imports, GET /imports/{batch_id},
// POST /imports/{batch_id}/decisions, POST /imports/field-reviews/{review_id}/resolve.

export type ImportBatchState = "processing" | "needs_review" | "completed" | "failed";

export type ImportRowOutcome = "accepted" | "needs_review" | "rejected" | "skipped";

/** Why an accepted row points at its clinic. */
export type ImportMatchBasis = "new_clinic" | "prior_import" | "staff_new_clinic" | "staff_link";

/** Why a row was paired with another row or clinic. Candidates only suggest; staff decide. */
export type CandidateBasis =
  "exact_name" | "similar_name" | "shared_email" | "shared_phone" | "prior_import";

/** 202 response to an upload. */
export interface ImportAccepted {
  batch_id: string;
  state: ImportBatchState;
  /** True when this exact file was imported before; the earlier batch is returned unchanged. */
  replayed: boolean;
}

export interface ImportCounts {
  created_clinics: number;
  accepted_rows: number;
  needs_review_rows: number;
  rejected_rows: number;
  skipped_rows: number;
}

/**
 * Another import row (import_row_id, sheet, row) or an existing clinic (clinic_id, clinic_name). The row
 * is from this upload or from an earlier upload still awaiting review. Once that row is accepted,
 * clinic_id and clinic_name name its clinic, so the rest of the group can be linked to it.
 */
export interface ImportRowCandidate {
  import_row_id: string | null;
  sheet: string | null;
  row: number | null;
  clinic_id: string | null;
  clinic_name: string | null;
  basis: CandidateBasis[];
}

export interface ImportRowResult {
  import_row_id: string;
  sheet: string;
  row: number;
  result: ImportRowOutcome;
  clinic_id: string | null;
  match_basis: ImportMatchBasis | null;
  /** Safe codes such as "missing_facility" or "invalid_email"; empty unless rejected. */
  reasons: string[];
  /** Safe codes such as "unmapped_status" or "numeric_contact_number". */
  warnings: string[];
  /** Rows sharing a review_group are decided together. */
  review_group: string | null;
  candidates: ImportRowCandidate[];
  /** Only for needs_review rows: the values a decision would import. */
  proposed_fields: Record<string, string> | null;
}

export interface FieldReview {
  review_id: string;
  clinic_id: string | null;
  field_name: string;
  state: "unresolved" | "resolved";
  resolved_value: string | null;
  /** The clinic's value now; it may be a dashboard edit made after the review opened. */
  current_value: string | null;
  /** Send back when resolving; the API answers 409 version_conflict if the clinic changed since. */
  clinic_version: number | null;
  candidate_rows: { import_row_id: string; sheet: string; row: number; value: string | null }[];
}

export interface ImportResult {
  batch_id: string;
  state: ImportBatchState;
  original_filename: string;
  uploaded_at: string;
  counts: ImportCounts;
  rows: ImportRowResult[];
  field_reviews: FieldReview[];
}

export interface ImportDecisionRequest {
  import_row_ids: string[];
  action: "create_clinic" | "link_clinic" | "reject";
  /** Required for link_clinic only. */
  clinic_id?: string;
  /** create_clinic only; required when the rows spell the clinic name differently. */
  clinic_name?: string;
  reason: string;
}

export interface FieldReviewResolution {
  /** A candidate value, a corrected value, or null to leave the field empty. */
  value: string | null;
  reason: string;
  /** The review's clinic_version as loaded. */
  clinic_version: number;
}
