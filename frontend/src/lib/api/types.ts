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
