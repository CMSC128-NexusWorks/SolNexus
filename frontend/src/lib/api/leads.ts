import { apiFetch } from "./client";
import type { HistoryPage, LeadsPage, LeadsQuery } from "./types";

export function getLeads(query: LeadsQuery = {}) {
  return apiFetch<LeadsPage>("/leads", { query: { ...query } });
}

export function getDueLeads() {
  return apiFetch<LeadsPage>("/leads/due");
}

export function getLeadHistory(clinicId: string, cursor?: string) {
  return apiFetch<HistoryPage>(`/leads/${clinicId}/history`, { query: { cursor } });
}
