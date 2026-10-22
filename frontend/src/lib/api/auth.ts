import { apiFetch } from "./client";
import type { LoginRequest, StaffUser } from "./types";

export function login(credentials: LoginRequest) {
  return apiFetch<StaffUser>("/auth/login", { method: "POST", body: credentials });
}

export function logout() {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}
