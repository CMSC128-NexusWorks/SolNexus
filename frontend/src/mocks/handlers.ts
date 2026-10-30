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
} from "@/lib/api/types";

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

function page(items: LeadRow[]): LeadsPage {
  const now = new Date();
  return {
    as_of: now.toISOString(),
    published_at: new Date(now.getTime() - 6 * 60_000).toISOString(),
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
    const user = mockSessionUser();
    return user ? HttpResponse.json(user) : unauthorized();
  }),

  http.get(api("/leads/due"), async () => {
    await delay(300);
    if (!mockSessionUser()) return unauthorized();
    return HttpResponse.json(page(dueRows()));
  }),

  http.get<{ clinicId: string }, never, HistoryPage | ApiErrorBody>(
    api("/leads/:clinicId/history"),
    async ({ params }) => {
      await delay(300);
      if (!mockSessionUser()) return unauthorized();
      const { clinicId } = params;
      if (!MOCK_LEADS.some((lead) => lead.clinic_id === clinicId)) {
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
    const params = new URL(request.url).searchParams;
    const status = params.get("status") as StatusCode | null;
    const q = params.get("q")?.trim().toLowerCase();
    const items = MOCK_LEADS.filter((lead) => {
      if (status && lead.status_code !== status) return false;
      if (!q) return true;
      return [lead.clinic_name, lead.contact_person, lead.email, lead.contact_number].some(
        (value) => value?.toLowerCase().includes(q),
      );
    });
    return HttpResponse.json(page(items));
  }),
];
