import { ApiError } from "@/lib/api/client";
import type { CandidateBasis } from "@/lib/api/types";

/**
 * Plain-language text for the import API's safe codes (docs/workbook-import.md). The API never sends
 * cell values in reasons or errors, so these strings are all staff ever see about a failed row.
 * Unknown codes fall back to the raw code so a new backend code is visible, not silently dropped.
 */
const REASONS: Record<string, string> = {
  missing_facility: "No clinic name",
  invalid_email: "Email address is not valid",
  value_too_long: "A cell is too long",
  rejected_by_staff: "Rejected by staff",
  rejected_by_staff_earlier: "Rejected by staff in an earlier upload",
};

const WARNINGS: Record<string, string> = {
  unmapped_status: "Status text not recognized, so status was left blank",
  numeric_contact_number: "Phone stored as a number in Excel, so a leading zero may be missing",
  unconfirmed_columns_held: "Extra columns kept aside until SolTech confirms what they mean",
};

const BASES: Record<CandidateBasis, string> = {
  exact_name: "same name",
  similar_name: "similar name",
  shared_email: "same email",
  shared_phone: "same phone",
  prior_import: "imported before",
};

export const reasonLabel = (code: string) => REASONS[code] ?? code;
export const warningLabel = (code: string) => WARNINGS[code] ?? code;
export const basisLabel = (basis: CandidateBasis) => BASES[basis] ?? basis;

/** Upload size limit enforced by the API (MAX_UPLOAD_BYTES); checked here first to skip a wasted upload. */
export const MAX_WORKBOOK_BYTES = 10 * 1024 * 1024;

/** Why an upload was refused, in words staff can act on. Every failure means nothing was imported. */
export function uploadErrorMessage(error: Error): string {
  if (!(error instanceof ApiError))
    return "Couldn't reach SolNexus. Check your connection and try again.";
  switch (error.code) {
    case "unsupported_file_type":
      return "Choose the lead workbook as an .xlsx file.";
    case "invalid_workbook":
      return "This file can't be read as an Excel workbook. It may be damaged, macro-enabled, or not really an .xlsx file.";
    case "workbook_too_large":
      return "The workbook is larger than 10 MB.";
    case "too_many_rows":
      return "The workbook has more than 10,000 filled rows, or data below row 20,000. Delete any stray cells far down the sheets and upload again.";
    case "unsupported_workbook_format": {
      // details name a sheet position or cell, never a value, so they are safe to show.
      const where = error.details.map((d) => d.message ?? d.reason ?? d.field).filter(Boolean);
      return [
        "The workbook layout doesn't match the expected lead sheets.",
        ...where.map((w) => `${w}.`),
      ].join(" ");
    }
  }
  if (error.isUnauthorized) return "Your session expired. Sign in again, then upload the file.";
  return "The upload failed and nothing was imported. Try uploading the file again.";
}
