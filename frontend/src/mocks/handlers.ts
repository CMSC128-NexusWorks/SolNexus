import { delay, http, HttpResponse } from "msw";

import type {
  ApiErrorBody,
  FieldReviewResolution,
  HistoryPage,
  ImportDecisionRequest,
  ImportResult,
  LeadRow,
  LeadsPage,
  StaffUser,
  StatusCode,
  PipelineStatus,
} from "@/lib/api/types";

import { getMockScenario } from "./scenarios";
import { MOCK_CREDENTIALS } from "./credentials";
import { businessDate, MOCK_HISTORY, MOCK_IMPORT_RESULT, MOCK_LEADS, MOCK_USER } from "./data";

// Mock implementation of the proposed /api/v1 contract. "*" matches any API origin.
const api = (path: string) => `*/api/v1${path}`;

function error(status: number, code: string, message: string) {
  return HttpResponse.json<ApiErrorBody>({ error: { code, message, details: [] } }, { status });
}

// Stands in for the server-side session behind the HttpOnly cookie. Kept per tab so a reload in
// mock mode stays signed in, like the real cookie.
const MOCK_SESSION_KEY = "solnexus.mock-session";

/** Start or end the mock API's session. Tests use it to begin signed in or signed out. */
export function setMockSession(user: StaffUser | null) {
  if (user) sessionStorage.setItem(MOCK_SESSION_KEY, JSON.stringify(user));
  else sessionStorage.removeItem(MOCK_SESSION_KEY);
}

function mockSessionUser(): StaffUser | null {
  const raw = sessionStorage.getItem(MOCK_SESSION_KEY);
  return raw ? (JSON.parse(raw) as StaffUser) : null;
}

const unauthorized = () => error(401, "unauthorized", "Sign in required");

// Per-tab mutable synthetic records let the mock demonstrate row edits without claiming a real import.
const originalLeads = structuredClone(MOCK_LEADS);
export function resetMockLeads() {
  MOCK_LEADS.splice(0, MOCK_LEADS.length, ...structuredClone(originalLeads));
}

/** Predictable synthetic failures exercise the same HTTP boundary as the real API. */
async function readFailure() {
  const scenario = getMockScenario();
  if (scenario === "loading") await delay(2000);
  if (scenario === "session-expired") return unauthorized();
  if (scenario === "api-error") return error(503, "data_unavailable", "Synthetic API unavailable");
  return null;
}

function validation(field: string, reason: string) {
  return HttpResponse.json<ApiErrorBody>(
    {
      error: {
        code: "validation_error",
        message: "Request validation failed",
        details: [{ field, reason }],
      },
    },
    { status: 422 },
  );
}

// A mock read must not advance publication time any more than a real read does.
const publishedSnapshot = Date.now() - 6 * 60_000;
function publicationTime() {
  return new Date(
    publishedSnapshot - (getMockScenario() === "pipeline-stale" ? 174 * 60_000 : 0),
  ).toISOString();
}

function page(items: LeadRow[]): LeadsPage {
  const now = new Date();
  return {
    as_of: now.toISOString(),
    published_at: publicationTime(),
    items,
    next_cursor: null,
  };
}

// Due rule from the contract: non-closed rows with next_action_date <= today (Manila), overdue first.
function dueRows(today = businessDate()) {
  return MOCK_LEADS.filter(
    (lead) =>
      lead.status_code !== "closed" &&
      lead.next_action_date !== null &&
      lead.next_action_date <= today,
  ).sort((a, b) => a.next_action_date!.localeCompare(b.next_action_date!));
}

// The mock import batch, changed by decisions and review resolutions. Tests can reset it.
let mockImport: ImportResult = structuredClone(MOCK_IMPORT_RESULT);

export function resetMockImport() {
  mockImport = structuredClone(MOCK_IMPORT_RESULT);
}

// Recount like the real API: needs_review while a row awaits a decision or a field review is open.
function recountMockImport() {
  const rows = mockImport.rows;
  const count = (result: string) => rows.filter((row) => row.result === result).length;
  const created = new Set(
    rows
      .filter((row) => row.match_basis === "new_clinic" || row.match_basis === "staff_new_clinic")
      .map((row) => row.clinic_id),
  );
  mockImport.counts = {
    created_clinics: created.size,
    accepted_rows: count("accepted"),
    needs_review_rows: count("needs_review"),
    rejected_rows: count("rejected"),
    skipped_rows: count("skipped"),
  };
  const openReview = mockImport.field_reviews.some((review) => review.state === "unresolved");
  mockImport.state = count("needs_review") > 0 || openReview ? "needs_review" : "completed";
}

export const handlers = [
  http.get(api("/pipeline/status"), async () => {
    if (!mockSessionUser()) return unauthorized();
    const failure = await readFailure();
    if (failure) return failure;
    const scenario = getMockScenario();
    const now = new Date();
    const published = publicationTime();
    const status = scenario === "pipeline-failed" ? ("failed" as const) : ("succeeded" as const);
    const payload: PipelineStatus = {
      as_of: now.toISOString(),
      published_at: published,
      last_run_status: status,
      is_stale: scenario === "pipeline-stale",
      stale_after_minutes: 120,
      pipelines: [
        {
          pipeline: "silver_publish",
          last_run_status: status,
          last_run_started_at: published,
          last_run_finished_at: now.toISOString(),
          last_succeeded_at: published,
          last_succeeded_data_as_of: published,
        },
      ],
    };
    return HttpResponse.json(payload);
  }),
  http.get(api("/leads/needs-name"), async () => {
    if (!mockSessionUser()) return unauthorized();
    const failure = await readFailure();
    if (failure) return failure;
    return HttpResponse.json(
      page(MOCK_LEADS.filter((r) => r.record_type === "inquiry" && !r.next_action_date)),
    );
  }),
  http.get(api("/leads/:id"), async ({ params, request }) => {
    if (!mockSessionUser()) return unauthorized();
    const failure = await readFailure();
    if (failure) return failure;
    if (params.id === "due") {
      const date = new URL(request.url).searchParams.get("date") ?? undefined;
      if (
        date &&
        (!/^\d{4}-\d{2}-\d{2}$/.test(date) ||
          Number.isNaN(Date.parse(date)) ||
          new Date(date).toISOString().slice(0, 10) !== date)
      )
        return validation("date", "Use an ISO business date");
      return HttpResponse.json(page(getMockScenario() === "empty-due" ? [] : dueRows(date)));
    }
    const row = MOCK_LEADS.find((r) => r.lead_id === params.id);
    return row ? HttpResponse.json(row) : error(404, "not_found", "Lead not found");
  }),

  ...(["clinics", "inquiries"] as const).map((kind) =>
    http.patch(api(`/${kind}/:id`), async ({ params, request }) => {
      if (!mockSessionUser()) return unauthorized();
      const row = MOCK_LEADS.find(
        (r) =>
          r.lead_id === params.id && r.record_type === (kind === "clinics" ? "clinic" : "inquiry"),
      );
      if (!row) return error(404, "not_found", "Lead not found");
      const body = (await request.json()) as Partial<LeadRow> & { reason?: string };
      if (!Number.isInteger(body.version) || (body.version ?? 0) < 1)
        return validation("version", "A positive version is required");
      if (body.version !== row.version)
        return error(409, "version_conflict", "This row changed. Refresh before retrying.");
      if (kind === "inquiries" && Object.prototype.hasOwnProperty.call(body, "clinic_name"))
        return error(
          422,
          "confirmation_evidence_required",
          "Clinic name requires staff-reviewed reply evidence",
        );
      const inquiryFields = [
        "contact_person",
        "contact_number",
        "email",
        "status_code",
        "next_action_date",
        "next_step",
        "calling_notes",
      ];
      const allowed =
        kind === "inquiries"
          ? inquiryFields
          : [
              ...inquiryFields,
              "clinic_name",
              "person_spoken_to",
              "region",
              "province",
              "municipality",
              "address",
            ];
      for (const [field, value] of Object.entries(body)) {
        if (![...allowed, "version", "reason"].includes(field))
          return validation(field, "This field is not editable for this record");
        if (
          field !== "version" &&
          value !== null &&
          (typeof value !== "string" || value.length > 4000)
        )
          return validation(field, "Use text or null");
      }
      if (
        body.clinic_name !== undefined &&
        (!body.clinic_name?.trim() ||
          (body.clinic_name !== row.clinic_name && !body.reason?.trim()))
      )
        return validation("clinic_name", "A name correction requires a nonblank name and reason");
      if (
        body.email !== undefined &&
        body.email !== null &&
        !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.email)
      )
        return validation("email", "Enter a valid email address");
      if (
        body.status_code !== undefined &&
        body.status_code !== null &&
        !["contacted", "proposal_sent", "awaiting_demo", "follow_up_needed", "closed"].includes(
          body.status_code,
        )
      )
        return validation("status_code", "Choose an approved status");
      if (
        body.next_action_date !== undefined &&
        body.next_action_date !== null &&
        (!/^\d{4}-\d{2}-\d{2}$/.test(body.next_action_date) ||
          Number.isNaN(Date.parse(body.next_action_date)) ||
          new Date(body.next_action_date).toISOString().slice(0, 10) !== body.next_action_date)
      )
        return validation("next_action_date", "Use an ISO business date");
      if (getMockScenario() === "validation-error")
        return validation("email", "Synthetic email validation error");
      const changes = Object.entries(body).filter(
        ([field, value]) => allowed.includes(field) && row[field as keyof LeadRow] !== value,
      );
      if (changes.length) {
        for (const [field, value] of changes) Object.assign(row, { [field]: value });
        row.version += 1;
        row.pending_projection = true;
      }
      return HttpResponse.json(row);
    }),
  ),

  // Seed inquiries have no recorded outbound question/reply pair; do not fake confirmation success.
  http.post(api("/inquiries/:id/confirm-clinic"), () =>
    mockSessionUser()
      ? error(
          422,
          "invalid_evidence",
          "Load persisted question/reply evidence through the real API to confirm this inquiry.",
        )
      : unauthorized(),
  ),
  http.post(api("/auth/login"), async ({ request }) => {
    const body = (await request.json()) as { email?: string; password?: string };
    await delay(300);
    if (body.email !== MOCK_CREDENTIALS.email || body.password !== MOCK_CREDENTIALS.password) {
      return error(401, "invalid_credentials", "Invalid email or password");
    }
    setMockSession(MOCK_USER);
    return HttpResponse.json(MOCK_USER);
  }),

  // Matches the real API: logout needs no live session and always succeeds.
  http.post(api("/auth/logout"), () => {
    setMockSession(null);
    return new HttpResponse(null, { status: 204 });
  }),

  http.get(api("/auth/session"), () => {
    if (getMockScenario() === "session-expired") return unauthorized();
    const user = mockSessionUser();
    return user ? HttpResponse.json(user) : unauthorized();
  }),

  http.get(api("/leads/due"), async () => {
    await delay(300);
    if (!mockSessionUser()) return unauthorized();
    const failure = await readFailure();
    if (failure) return failure;
    return HttpResponse.json(page(getMockScenario() === "empty-due" ? [] : dueRows()));
  }),

  http.get<{ clinicId: string }, never, HistoryPage | ApiErrorBody>(
    api("/leads/:clinicId/history"),
    async ({ params }) => {
      await delay(300);
      if (!mockSessionUser()) return unauthorized();
      const failure = await readFailure();
      if (failure) return failure;
      const { clinicId } = params;
      if (!MOCK_LEADS.some((lead) => lead.lead_id === clinicId)) {
        return error(404, "not_found", "Lead not found");
      }
      return HttpResponse.json({
        clinic_id: clinicId,
        items: MOCK_HISTORY[clinicId] ?? [],
        next_cursor: null,
      });
    },
  ),

  http.post(api("/imports"), async () => {
    await delay(300);
    if (!mockSessionUser()) return unauthorized();
    return HttpResponse.json(
      { batch_id: mockImport.batch_id, state: mockImport.state, replayed: false },
      { status: 202 },
    );
  }),

  http.get<{ batchId: string }>(api("/imports/:batchId"), async ({ params }) => {
    await delay(300);
    if (!mockSessionUser()) return unauthorized();
    if (params.batchId !== mockImport.batch_id)
      return error(404, "not_found", "Import batch not found");
    return HttpResponse.json(mockImport);
  }),

  // Simplified decision: marks rows accepted or rejected. For create_clinic over rows whose phones
  // differ it opens a contact_number review, as the real API does for any disagreeing field.
  http.post<{ batchId: string }, ImportDecisionRequest>(
    api("/imports/:batchId/decisions"),
    async ({ params, request }) => {
      await delay(300);
      if (!mockSessionUser()) return unauthorized();
      if (params.batchId !== mockImport.batch_id)
        return error(404, "not_found", "Import batch not found");
      const body = await request.json();
      const rows = mockImport.rows.filter((row) => body.import_row_ids.includes(row.import_row_id));
      if (rows.some((row) => row.result !== "needs_review")) {
        return error(
          409,
          "row_already_decided",
          "Some rows were already decided; reload the import",
        );
      }
      const clinicId = body.clinic_id ?? crypto.randomUUID();
      for (const row of rows) {
        row.result = body.action === "reject" ? "rejected" : "accepted";
        row.clinic_id = body.action === "reject" ? null : clinicId;
        row.match_basis =
          body.action === "reject"
            ? null
            : body.action === "link_clinic"
              ? "staff_link"
              : "staff_new_clinic";
        row.reasons = body.action === "reject" ? ["rejected_by_staff"] : [];
        row.candidates = [];
        row.review_group = null;
      }
      const phones = new Set(
        rows.map((row) => row.proposed_fields?.contact_number).filter(Boolean),
      );
      if (body.action === "create_clinic" && phones.size > 1) {
        mockImport.field_reviews.push({
          review_id: crypto.randomUUID(),
          clinic_id: clinicId,
          field_name: "contact_number",
          state: "unresolved",
          resolved_value: null,
          candidate_rows: rows.map((row) => ({
            import_row_id: row.import_row_id,
            sheet: row.sheet,
            row: row.row,
            value: row.proposed_fields?.contact_number ?? null,
          })),
        });
      }
      // Like the real API, a row still in review shows the clinic its decided candidate rows now belong to,
      // so staff can link the rest of the group there instead of creating the clinic twice.
      if (body.action !== "reject") {
        const decided = new Set(rows.map((row) => row.import_row_id));
        const clinicName =
          body.action === "create_clinic"
            ? (body.clinic_name ?? rows[0]?.proposed_fields?.clinic_name ?? null)
            : null;
        for (const row of mockImport.rows) {
          for (const candidate of row.candidates) {
            if (candidate.import_row_id && decided.has(candidate.import_row_id)) {
              candidate.clinic_id = clinicId;
              candidate.clinic_name = clinicName;
            }
          }
        }
      }
      for (const row of rows) row.proposed_fields = null;
      recountMockImport();
      return HttpResponse.json(mockImport);
    },
  ),

  http.post<{ reviewId: string }, FieldReviewResolution>(
    api("/imports/field-reviews/:reviewId/resolve"),
    async ({ params, request }) => {
      await delay(300);
      if (!mockSessionUser()) return unauthorized();
      const review = mockImport.field_reviews.find((item) => item.review_id === params.reviewId);
      if (!review) return error(404, "not_found", "Field review not found");
      if (review.state === "resolved") {
        return error(
          409,
          "review_already_resolved",
          "This field review was already resolved; reload the import",
        );
      }
      const body = await request.json();
      review.state = "resolved";
      review.resolved_value = body.value?.trim() || null;
      recountMockImport();
      return HttpResponse.json(review);
    },
  ),

  http.get(api("/leads"), async ({ request }) => {
    await delay(300);
    if (!mockSessionUser()) return unauthorized();
    const failure = await readFailure();
    if (failure) return failure;
    if (getMockScenario() === "no-results") return HttpResponse.json(page([]));
    const params = new URL(request.url).searchParams;
    const status = params.get("status") as StatusCode | null;
    const q = params.get("q")?.trim().toLowerCase();
    const items = MOCK_LEADS.filter((lead) => {
      if (status && lead.status_code !== status) return false;
      if (
        params.get("next_action_date") &&
        lead.next_action_date !== params.get("next_action_date")
      )
        return false;
      if (!q) return true;
      return [lead.clinic_name, lead.contact_person, lead.email, lead.contact_number].some(
        (value) => value?.toLowerCase().includes(q),
      );
    });
    return HttpResponse.json(page(items));
  }),
];
