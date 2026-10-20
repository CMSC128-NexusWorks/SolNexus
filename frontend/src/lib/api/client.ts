import type { ApiErrorBody } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** Error thrown for any non-2xx response, using the contract's JSON error shape. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ApiErrorBody["error"]["details"];

  constructor(status: number, body: ApiErrorBody | null) {
    super(body?.error.message ?? `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = body?.error.code ?? "unknown_error";
    this.details = body?.error.details ?? [];
  }

  /** 401: no valid session. The UI should send the user back to sign-in. */
  get isUnauthorized() {
    return this.status === 401;
  }

  /** 409: someone else edited the record first. */
  get isConflict() {
    return this.status === 409;
  }
}

type Query = Record<string, string | number | undefined>;

interface RequestOptions extends Omit<RequestInit, "body"> {
  query?: Query;
  body?: unknown;
}

function buildUrl(path: string, query?: Query) {
  const url = new URL(`/api/v1${path}`, API_URL);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }
  return url.toString();
}

/**
 * The single way screens talk to the backend. Sends the session cookie,
 * encodes JSON bodies and throws ApiError on failure.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { query, body, headers, ...init } = options;
  const response = await fetch(buildUrl(path, query), {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(body !== undefined && { "Content-Type": "application/json" }),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    const errorBody = (await response.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(response.status, errorBody);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
