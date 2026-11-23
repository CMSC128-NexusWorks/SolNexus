import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  confirmClinic,
  getDueLeads,
  getLead,
  getLeadHistory,
  getLeads,
  getNeedsName,
  getPipelineStatus,
  updateLead,
  type Confirmation,
  type RowChanges,
} from "@/lib/api/leads";
import type { LeadRow, LeadsQuery } from "@/lib/api/types";

// One key family and invalidation policy serves every table, detail view and mutation.
export const leadKeys = {
  all: ["leads"] as const,
  list: (query: LeadsQuery) => ["leads", "list", query] as const,
  due: () => ["leads", "due"] as const,
  needsName: () => ["leads", "needs-name"] as const,
  detail: (id: string) => ["leads", "detail", id] as const,
  history: (id: string) => ["leads", "history", id] as const,
};
export const pipelineKey = ["pipeline", "status"] as const;

/** Paging is owned by the shared hook; filters create a fresh cursor/cache entry. */
export function useLeads(query: LeadsQuery = {}, enabled = true) {
  return useInfiniteQuery({
    queryKey: leadKeys.list(query),
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => getLeads({ ...query, cursor: pageParam }),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}
export function useDueLeads(enabled = true) {
  return useInfiniteQuery({
    queryKey: leadKeys.due(),
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => getDueLeads(pageParam),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}
export function useNeedsName(enabled = true) {
  return useInfiniteQuery({
    queryKey: leadKeys.needsName(),
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => getNeedsName(pageParam),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}
export function useLead(id: string) {
  return useQuery({
    queryKey: leadKeys.detail(id),
    queryFn: () => getLead(id),
    enabled: Boolean(id),
  });
}
export function useLeadHistory(id: string) {
  return useInfiniteQuery({
    queryKey: leadKeys.history(id),
    enabled: Boolean(id),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => getLeadHistory(id, pageParam),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}
/** Pipeline polling uses its own endpoint; list traffic does not masquerade as pipeline health. */
export function usePipelineStatus() {
  return useQuery({ queryKey: pipelineKey, queryFn: getPipelineStatus, refetchInterval: 60_000 });
}
export function useLeadUpdate(row: LeadRow, onSaved: () => void) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ changes, reason }: { changes: RowChanges; reason: string }) =>
      updateLead(row, changes, reason),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: leadKeys.all });
      onSaved();
    },
  });
}
export function useClinicConfirmation(id: string, onConfirmed: (lead: LeadRow) => void) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Confirmation) => confirmClinic(id, body),
    onSuccess: async (lead) => {
      // A closed inquiry ceases to be a readable lead: evict it before refetching active tables.
      client.removeQueries({ queryKey: leadKeys.detail(id) });
      client.removeQueries({ queryKey: leadKeys.history(id) });
      onConfirmed(lead);
      await client.invalidateQueries({ queryKey: leadKeys.all });
    },
  });
}
export function useRefreshLeads() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: leadKeys.all });
}
