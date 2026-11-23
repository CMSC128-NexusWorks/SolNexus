import { useState, type FormEvent } from "react";
import { useLeadUpdate, useRefreshLeads } from "./queries";
import { Input } from "@/components/ui/input";
import { FieldSelect } from "./field-select";
import { type RowChanges } from "@/lib/api/leads";
import { ApiError } from "@/lib/api/client";
import { STATUS_LABELS, type LeadRow, type StatusCode } from "@/lib/api/types";
import { Button } from "@/components/ui/button";

const fields = {
  clinic_name: "Clinic name",
  contact_person: "Contact person",
  contact_number: "Contact number",
  email: "Email",
  next_action_date: "Next-action date",
  next_step: "Next step",
  calling_notes: "Notes",
  person_spoken_to: "Person spoken to",
  region: "Region",
  province: "Province",
  municipality: "Municipality",
  address: "Address",
} as const;

/** A draft never mutates cached rows; cancellation discards it and save sends changed fields only. */
export function RowEditor({ row, close }: { row: LeadRow; close: () => void }) {
  const refresh = useRefreshLeads();
  const [draft, setDraft] = useState<RowChanges>({});
  const [reason, setReason] = useState("");
  const mutation = useLeadUpdate(row, close);
  const error = mutation.error;
  function submit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate({ changes: draft, reason });
  }
  return (
    <form
      noValidate
      onSubmit={submit}
      className="my-3 grid gap-3 rounded-md border bg-muted/30 p-4"
      aria-label={`Edit ${row.clinic_name ?? "inquiry"}`}
    >
      <h3 className="font-semibold">Edit {row.clinic_name ?? "Clinic name unknown"}</h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(fields)
          .filter(
            ([field]) =>
              row.record_type === "clinic" ||
              ![
                "clinic_name",
                "person_spoken_to",
                "region",
                "province",
                "municipality",
                "address",
              ].includes(field),
          )
          .map(([field, label]) => {
            const key = field as keyof typeof fields;
            const issue =
              error instanceof ApiError ? error.details.find((d) => d.field === key) : undefined;
            const issueId = `${row.lead_id}-${key}-error`;
            return (
              <label key={key} className="grid gap-1 text-sm">
                {label}
                <Input
                  aria-label={label}
                  className="rounded border bg-background p-2"
                  type={key === "next_action_date" ? "date" : key === "email" ? "email" : "text"}
                  aria-invalid={Boolean(issue)}
                  aria-describedby={issue ? issueId : undefined}
                  maxLength={4000}
                  required={key === "clinic_name"}
                  value={
                    (Object.prototype.hasOwnProperty.call(draft, key) ? draft[key] : row[key]) ?? ""
                  }
                  onChange={(e) => setDraft({ ...draft, [key]: e.target.value || null })}
                />
                {issue && (
                  <span id={issueId} className="text-destructive">
                    {issue.reason ?? issue.message}
                  </span>
                )}
              </label>
            );
          })}
        <FieldSelect
          label="Status"
          value={
            (Object.prototype.hasOwnProperty.call(draft, "status_code")
              ? draft.status_code
              : row.status_code) ?? ""
          }
          onChange={(value) =>
            setDraft({ ...draft, status_code: (value || null) as StatusCode | null })
          }
          options={[
            { value: "", label: "Unknown" },
            ...Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label })),
          ]}
        />
        <label className="grid gap-1 text-sm">
          Reason (required for a name correction)
          <Input
            className="rounded border bg-background p-2"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
      </div>
      {error && (
        <div role="alert">
          {error instanceof ApiError && error.isConflict
            ? "Someone changed this row. Refresh before retrying; your draft has not been saved."
            : error.message}
          {error instanceof ApiError &&
            error.details.map((d, i) => (
              <p key={i}>
                {d.field}: {d.reason ?? (d as { message?: string }).message}
              </p>
            ))}
          {error instanceof ApiError && error.isConflict && (
            <Button
              type="button"
              variant="outline"
              onClick={async () => {
                await refresh();
                close();
              }}
            >
              Refresh row
            </Button>
          )}
        </div>
      )}
      <div className="flex gap-2">
        <Button
          disabled={
            mutation.isPending ||
            Object.keys(draft).length === 0 ||
            (error instanceof ApiError && error.isConflict)
          }
        >
          {mutation.isPending ? "Saving…" : "Save row"}
        </Button>
        <Button variant="outline" type="button" disabled={mutation.isPending} onClick={close}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
