import type { ImportResult, Interaction, LeadRow, StaffUser } from "@/lib/api/types";

// Synthetic data only: invented clinics, example.test emails, placeholder numbers.
// Never paste real client rows here (see docs/implementation_roadmap.md).
// Shapes follow docs/contracts/fixtures/phase1-api-examples-v1.json.

export const MOCK_USER: StaffUser = {
  user_id: "00000000-0000-4000-8000-000000000001",
  email: "staff@example.test",
};

/** Today's Asia/Manila business date as YYYY-MM-DD, offset by `days`. */
export function businessDate(days = 0, now = new Date()) {
  const shifted = new Date(now.getTime() + days * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Manila" }).format(shifted);
}

function daysAgo(days: number, hour = 9) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  date.setUTCHours(hour, 0, 0, 0);
  return date.toISOString();
}

const clinicId = (n: number) => `10000000-0000-4000-8000-${String(n).padStart(12, "0")}`;

export const MOCK_LEADS: LeadRow[] = [
  {
    lead_id: clinicId(1),
    record_type: "clinic",
    clinic_id: clinicId(1),
    clinic_name: "Harborview Clinic",
    clinic_name_state: "confirmed",
    contact_person: "Sam Example",
    contact_number: "0917 000 0101",
    email: "harborview@example.test",
    status_code: "proposal_sent",
    next_action_date: businessDate(-2),
    next_step: "Follow-up call agreed",
    last_contact_at: daysAgo(7),
    channels: ["gmail"],
    version: 1,
  },
  {
    lead_id: clinicId(2),
    record_type: "clinic",
    clinic_id: clinicId(2),
    clinic_name: "Riverside Family Clinic",
    clinic_name_state: "confirmed",
    contact_person: "Alex Sample",
    contact_number: "0918 000 0202",
    email: "riverside@example.test",
    status_code: "follow_up_needed",
    next_action_date: businessDate(0),
    next_step: "Asked us to call back this week",
    last_contact_at: daysAgo(7),
    channels: ["gmail"],
    version: 1,
  },
  {
    lead_id: clinicId(3),
    record_type: "clinic",
    clinic_id: clinicId(3),
    clinic_name: "Lakeside Diagnostics",
    clinic_name_state: "confirmed",
    contact_person: "Jordan Placeholder",
    contact_number: "0920 000 0303",
    email: "lakeside@example.test",
    status_code: "awaiting_demo",
    next_action_date: businessDate(0),
    next_step: "Waiting on their admin to confirm",
    last_contact_at: daysAgo(9),
    channels: ["gmail"],
    version: 1,
  },
  {
    lead_id: clinicId(4),
    record_type: "clinic",
    clinic_id: clinicId(4),
    clinic_name: "Hilltop Pediatrics",
    clinic_name_state: "confirmed",
    contact_person: "Casey Test",
    contact_number: "0915 000 0404",
    email: null,
    status_code: "contacted",
    next_action_date: businessDate(3),
    next_step: "No answer, try again",
    last_contact_at: daysAgo(3),
    channels: ["gmail"],
    version: 1,
  },
  {
    lead_id: clinicId(5),
    record_type: "clinic",
    clinic_id: clinicId(5),
    clinic_name: "Meadow Wellness",
    clinic_name_state: "confirmed",
    contact_person: "Robin Demo",
    contact_number: "0917 000 0505",
    email: "meadow@example.test",
    status_code: "closed",
    next_action_date: businessDate(-5),
    last_contact_at: daysAgo(18),
    channels: ["gmail"],
    version: 1,
  },
  {
    lead_id: clinicId(6),
    record_type: "clinic",
    clinic_id: clinicId(6),
    clinic_name: "Seaside Dental & Medical",
    clinic_name_state: "confirmed",
    contact_person: null,
    contact_number: "0921 000 0606",
    email: null,
    status_code: null,
    next_action_date: null,
    last_contact_at: null,
    channels: [],
    version: 1,
  },
  {
    lead_id: "70000000-0000-4000-8000-000000000001",
    record_type: "inquiry",
    clinic_id: null,
    clinic_name: null,
    clinic_name_state: "unknown",
    contact_person: null,
    contact_number: null,
    email: "newlead@example.test",
    status_code: null,
    next_action: "request_clinic_name",
    next_action_date: null,
    last_contact_at: daysAgo(1, 2),
    channels: ["gmail"],
    version: 1,
  },
];

export const MOCK_HISTORY: Record<string, Interaction[]> = {
  [clinicId(3)]: [
    {
      raw_message_id: "30000000-0000-4000-8000-000000000003",
      channel: "gmail",
      direction: "inbound",
      event_at: daysAgo(9, 6),
      excerpt: "Thanks for the proposal. Let me check with our admin about scheduling the demo.",
      topic: null,
      derived_status_code: "awaiting_demo",
    },
    {
      raw_message_id: "30000000-0000-4000-8000-000000000002",
      channel: "gmail",
      direction: "outbound",
      event_at: daysAgo(13, 1),
      excerpt: "Sending over the proposal and pricing we discussed.",
      topic: null,
      derived_status_code: "proposal_sent",
    },
    {
      raw_message_id: "30000000-0000-4000-8000-000000000001",
      channel: "gmail",
      direction: "inbound",
      event_at: daysAgo(19, 12),
      excerpt: "Interested in your EMR. How much per month?",
      topic: null,
      derived_status_code: null,
    },
  ],
};

const importRowId = (n: number) => `30000000-0000-4000-8000-${String(n).padStart(12, "0")}`;

/**
 * The contract's synthetic workbook right after upload: Harborview is on both sheets, so its two rows
 * wait for a staff decision; rows without a facility are rejected.
 */
export const MOCK_IMPORT_RESULT: ImportResult = {
  batch_id: "20000000-0000-4000-8000-000000000001",
  state: "needs_review",
  original_filename: "synthetic-lead-import-v1.xlsx",
  uploaded_at: "2026-10-30T07:00:00Z",
  counts: {
    created_clinics: 2,
    accepted_rows: 2,
    needs_review_rows: 2,
    rejected_rows: 2,
    skipped_rows: 0,
  },
  rows: [
    {
      import_row_id: importRowId(1),
      sheet: "Jacks Calling Sheet",
      row: 2,
      result: "needs_review",
      clinic_id: null,
      match_basis: null,
      reasons: [],
      warnings: ["unconfirmed_columns_held"],
      review_group: importRowId(1),
      candidates: [
        {
          import_row_id: importRowId(4),
          sheet: "Ljs Calling Sheet",
          row: 1,
          clinic_id: null,
          clinic_name: null,
          basis: ["exact_name", "shared_email"],
        },
      ],
      proposed_fields: {
        clinic_name: "Harborview Clinic",
        contact_number: "0917 000 0199",
        email: "harborview@example.test",
        status_code: "contacted",
        next_step: "Call next week",
      },
    },
    {
      import_row_id: importRowId(2),
      sheet: "Jacks Calling Sheet",
      row: 3,
      result: "rejected",
      clinic_id: null,
      match_basis: null,
      reasons: ["missing_facility"],
      warnings: [],
      review_group: null,
      candidates: [],
      proposed_fields: null,
    },
    {
      import_row_id: importRowId(3),
      sheet: "Jacks Calling Sheet",
      row: 4,
      result: "accepted",
      clinic_id: clinicId(3),
      match_basis: "new_clinic",
      reasons: [],
      warnings: [],
      review_group: null,
      candidates: [],
      proposed_fields: null,
    },
    {
      import_row_id: importRowId(4),
      sheet: "Ljs Calling Sheet",
      row: 1,
      result: "needs_review",
      clinic_id: null,
      match_basis: null,
      reasons: [],
      warnings: [],
      review_group: importRowId(1),
      candidates: [
        {
          import_row_id: importRowId(1),
          sheet: "Jacks Calling Sheet",
          row: 2,
          clinic_id: null,
          clinic_name: null,
          basis: ["exact_name", "shared_email"],
        },
      ],
      proposed_fields: {
        clinic_name: "Harborview Clinic",
        contact_number: "0917 000 0101",
        email: "harborview@example.test",
        calling_notes: "Asked for a follow-up email",
        person_spoken_to: "Sam Example",
        contact_person: "Sam Example",
      },
    },
    {
      import_row_id: importRowId(5),
      sheet: "Ljs Calling Sheet",
      row: 2,
      result: "rejected",
      clinic_id: null,
      match_basis: null,
      reasons: ["missing_facility"],
      warnings: [],
      review_group: null,
      candidates: [],
      proposed_fields: null,
    },
    {
      import_row_id: importRowId(6),
      sheet: "Ljs Calling Sheet",
      row: 3,
      result: "accepted",
      clinic_id: clinicId(4),
      match_basis: "new_clinic",
      reasons: [],
      warnings: [],
      review_group: null,
      candidates: [],
      proposed_fields: null,
    },
  ],
  field_reviews: [],
};
