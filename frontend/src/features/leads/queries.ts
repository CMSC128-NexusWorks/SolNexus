import { useQuery } from "@tanstack/react-query";

import { getDueLeads, getLeadHistory, getLeads } from "@/lib/api/leads";
import type { LeadsQuery } from "@/lib/api/types";

// Query keys live here so screens share cached data instead of refetching.
export const leadKeys = {
  all: ["leads"] as const,
  list: (query: LeadsQuery) => [...leadKeys.all, "list", query] as const,
  due: () => [...leadKeys.all, "due"] as const,
  history: (clinicId: string) => [...leadKeys.all, "history", clinicId] as const,
};

/** All leads, with optional status filter and clinic/contact search. */
export function useLeads(query: LeadsQuery = {}) {
  return useQuery({
    queryKey: leadKeys.list(query),
    queryFn: () => getLeads(query),
  });
}

/** Due today, including overdue rows. */
export function useDueLeads() {
  return useQuery({
    queryKey: leadKeys.due(),
    queryFn: getDueLeads,
  });
}

/** Linked interactions for one clinic, ordered by event time. */
export function useLeadHistory(clinicId: string | undefined) {
  return useQuery({
    queryKey: leadKeys.history(clinicId ?? ""),
    queryFn: () => getLeadHistory(clinicId!),
    enabled: Boolean(clinicId),
  });
}
