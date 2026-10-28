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
  /** UTC instant; null when no linked interaction has a trustworthy event time. */
  last_contact_at?: string | null;
  channels?: Channel[];
  /** Send back unchanged on every edit; the API returns 409 if someone saved first. */
  version: number;
  /** True when a staff edit is visible before the next silver refresh. */
  pending_projection?: boolean;
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

export interface LeadsQuery {
  status?: StatusCode;
  q?: string;
  limit?: number;
  cursor?: string;
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
}

export interface HistoryPage {
  clinic_id: string;
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
    details: { field?: string; reason?: string }[];
  };
}
