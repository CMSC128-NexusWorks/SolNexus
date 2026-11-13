import { apiFetch } from "./client";
import type { ImportAccepted, ImportResult } from "./types";

/**
 * Upload the legacy lead workbook (FR-02, SNX-28). The server imports it before answering 202, so the
 * returned batch is already final; read its rows with getImport. Re-uploading an identical file
 * returns the earlier batch with replayed: true and writes nothing.
 */
export function uploadWorkbook(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<ImportAccepted>("/imports", { method: "POST", body: form });
}

export const getImport = (batchId: string) => apiFetch<ImportResult>(`/imports/${batchId}`);
