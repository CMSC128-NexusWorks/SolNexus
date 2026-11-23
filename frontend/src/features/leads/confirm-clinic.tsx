import { useState, useId, type FormEvent } from "react";
import { useNavigate } from "react-router";
import type { Interaction, LeadRow } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { FieldSelect } from "./field-select";
import { useLeads, useClinicConfirmation } from "./queries";

/** Name confirmation is a reviewed identity decision, never an automatic inference from a message. */
export function ConfirmClinic({ row, messages }: { row: LeadRow; messages: Interaction[] }) {
  const [name, setName] = useState("");
  const [clinic, setClinic] = useState("");
  const [question, setQuestion] = useState("");
  const [reply, setReply] = useState("");
  const [reason, setReason] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [validation, setValidation] = useState("");
  const reviewId = useId();
  const navigate = useNavigate();
  const candidates = useLeads({ q: name, limit: 20 }, name.trim().length > 2);
  const rows = candidates.data?.pages.flatMap((page) => page.items) ?? [];
  const mutation = useClinicConfirmation(row.lead_id, (lead) =>
    navigate(`/leads/${lead.lead_id}`, { replace: true }),
  );
  function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || !question || !reply || !reason.trim() || !reviewed) {
      setValidation(
        "Enter a clinic name, select question and reply, and confirm your evidence review.",
      );
      return;
    }
    setValidation("");
    mutation.mutate({
      version: row.version,
      clinic_name: name,
      clinic_id: clinic || undefined,
      question_message_id: question,
      reply_message_id: reply,
      reason,
      confirm_source_mapping: true,
    });
  }
  return (
    <form
      onSubmit={submit}
      className="grid gap-3 rounded border p-4"
      aria-label="Confirm clinic name"
    >
      <h2 className="text-lg font-semibold">Confirm clinic name from a reviewed reply</h2>
      <p>
        The question and reply must be recorded by ingestion. Opening an email draft does not record
        a sent question.
      </p>
      <label className="grid gap-1">
        Confirmed clinic name
        <Input
          required
          maxLength={300}
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setClinic("");
          }}
        />
      </label>
      <FieldSelect
        label="Associate with a clinic"
        value={clinic}
        options={[
          { value: "", label: "Create a clinic with this confirmed name" },
          ...rows
            .filter((r) => r.record_type === "clinic")
            .map((r) => ({
              value: r.lead_id,
              label: `${r.clinic_name} — ${r.email ?? r.contact_person ?? "No contact recorded"}`,
            })),
        ]}
        onChange={(value) => {
          setClinic(value);
          const selected = rows.find((r) => r.clinic_id === value);
          if (selected?.clinic_name) setName(selected.clinic_name);
        }}
      />
      {(
        [
          ["outbound", "Question", question, setQuestion],
          ["inbound", "Reply", reply, setReply],
        ] as const
      ).map(([direction, label, value, setter]) => (
        <FieldSelect
          key={direction}
          label={label}
          value={value}
          onChange={setter}
          required
          options={[
            { value: "", label: `Select reviewed ${label.toLowerCase()}` },
            ...messages
              .filter((m) => m.direction === direction)
              .map((m) => ({
                value: m.raw_message_id,
                label: `${m.event_at ?? "Time unknown"} — ${m.excerpt ?? m.raw_message_id}`,
              })),
          ]}
        />
      ))}
      <label className="grid gap-1">
        Evidence review reason
        <Input
          required
          maxLength={4000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <div className="flex items-center gap-2">
        <Checkbox
          id={reviewId}
          checked={reviewed}
          onCheckedChange={(value) => setReviewed(value === true)}
        />
        <Label htmlFor={reviewId}>
          I reviewed this reply and confirm this exact source identity belongs to this clinic.
        </Label>
      </div>
      {validation && <p role="alert">{validation}</p>}
      {mutation.error && (
        <p role="alert">{mutation.error.message} Refresh the record if it changed.</p>
      )}
      <Button disabled={mutation.isPending}>
        {mutation.isPending ? "Confirming…" : "Confirm clinic"}
      </Button>
    </form>
  );
}
