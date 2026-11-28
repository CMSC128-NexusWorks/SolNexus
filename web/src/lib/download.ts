// Saving files the API returns, such as the current lead export (FR-19, SNX-53).

// The contract only says "spreadsheet", so the extension follows what the server actually sent.
// Content-Type is a CORS-safelisted response header, so it is readable even when the API is on
// another origin; Content-Disposition is not unless the API exposes it, so the name is built here.
const EXTENSIONS: Record<string, string> = {
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
  "text/csv": "csv",
};

/** "solnexus-leads-2026-11-15.xlsx": dated by the Asia/Manila business calendar, like due dates. */
export function exportFilename(contentType: string, now = new Date()) {
  const date = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Manila" }).format(now);
  const type = contentType.split(";")[0].trim().toLowerCase();
  return `solnexus-leads-${date}.${EXTENSIONS[type] ?? "xlsx"}`;
}

/** Hands a downloaded Blob to the browser's normal "save file" behaviour. */
export function saveFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  // Firefox ignores clicks on links that are not in the document.
  document.body.append(link);
  link.click();
  link.remove();
  // Revoke on a later tick: some browsers start reading the object URL only after click() returns.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
