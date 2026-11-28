import { apiFetch } from "./client";
import type { LoginRequest, StaffUser } from "./types";

export function login(credentials: LoginRequest) {
  return apiFetch<StaffUser>("/auth/login", { method: "POST", body: credentials });
}

export function logout() {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

/** Who is signed in. The session cookie is HttpOnly, so only the API can answer; 401 when signed out. */
export function getSession() {
  return apiFetch<StaffUser>("/auth/session");
}
