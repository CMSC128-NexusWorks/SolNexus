import { delay, http, HttpResponse } from "msw";

import type {
  ApiErrorBody,
  HistoryPage,
  LeadRow,
  LeadsPage,
  StaffUser,
  StatusCode,
} from "@/lib/api/types";

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

  http.post(api("/auth/logout"), () => {
    if (!mockSessionUser()) return unauthorized();
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
