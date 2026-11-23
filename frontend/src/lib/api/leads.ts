import { apiFetch } from "./client";
import type { HistoryPage, LeadRow, LeadsPage, LeadsQuery, PipelineStatus } from "./types";

export function getLeads(query: LeadsQuery = {}) {
  return apiFetch<LeadsPage>("/leads", { query: { ...query } });
}

export function getDueLeads(cursor?: string, date?: string) {
  return apiFetch<LeadsPage>("/leads/due", { query: { cursor, date } });
}

/** Publication and health come from Airflow's ledger, never from a browser or dbt build timer. */
export const getPipelineStatus = () => apiFetch<PipelineStatus>("/pipeline/status");

/** Detail and writes use the same operational record shown in every dashboard table. */
export const getLead = (id: string) => apiFetch<LeadRow>(`/leads/${id}`);
export const getNeedsName = (cursor?: string) =>
  apiFetch<LeadsPage>("/leads/needs-name", { query: { cursor } });
export type RowChanges = Partial<
  Pick<
    LeadRow,
    | "clinic_name"
    | "contact_person"
    | "contact_number"
    | "email"
    | "status_code"
    | "next_action_date"
    | "next_step"
    | "calling_notes"
    | "person_spoken_to"
    | "region"
    | "province"
    | "municipality"
    | "address"
  >
>;
export const updateLead = (row: LeadRow, changes: RowChanges, reason: string) =>
  apiFetch<LeadRow>(`/${row.record_type === "clinic" ? "clinics" : "inquiries"}/${row.lead_id}`, {
    method: "PATCH",
    body: { ...changes, version: row.version, reason },
  });
export interface Confirmation {
  version: number;
  clinic_name: string;
  clinic_id?: string;
  question_message_id: string;
  reply_message_id: string;
  confirm_source_mapping: true;
  reason: string;
}
export const confirmClinic = (id: string, body: Confirmation) =>
  apiFetch<LeadRow>(`/inquiries/${id}/confirm-clinic`, { method: "POST", body });

export function getLeadHistory(clinicId: string, cursor?: string) {
  return apiFetch<HistoryPage>(`/leads/${clinicId}/history`, { query: { cursor } });
}
