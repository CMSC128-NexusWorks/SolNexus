import { delay, http, HttpResponse } from "msw";

import type {
  ApiErrorBody,
  HistoryPage,
  LeadRow,
  LeadsPage,
  StaffUser,
  StatusCode,
  PipelineStatus,
} from "@/lib/api/types";

import { getMockScenario } from "./scenarios";
import { MOCK_CREDENTIALS } from "./credentials";
import { businessDate, MOCK_HISTORY, MOCK_LEADS, MOCK_USER } from "./data";

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
