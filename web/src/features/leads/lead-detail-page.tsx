import { useLead, useLeadHistory } from "./queries";
import { Link, useLocation, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { DataState } from "./data-state";
import { LeadTable } from "./lead-table";
import { ConfirmClinic } from "./confirm-clinic";

/** History paginates separately and retains the originating list's filters. */
export function LeadDetailPage() {
  const { clinicId = "" } = useParams();
  const location = useLocation();
  const lead = useLead(clinicId);
  const history = useLeadHistory(clinicId);
  const messages = history.data?.pages.flatMap((p) => p.items) ?? [];
  const returnTo = (location.state as { returnTo?: string } | null)?.returnTo ?? "/";
  return (
    <div className="grid gap-6">
      <Link className="underline" to={returnTo}>
        ← Back to leads
      </Link>
      <h1 className="text-3xl font-semibold">
        {lead.data?.clinic_name ?? (lead.data ? "Clinic name unknown" : "Lead detail")}
      </h1>
      <DataState pending={lead.isPending} error={lead.error} retry={() => void lead.refetch()} />
      {lead.data && <LeadTable rows={[lead.data]} empty="Lead not found." />}
      <section aria-labelledby="history-heading" className="grid gap-3">
        <h2 id="history-heading" className="text-lg font-semibold">
          Interaction history
        </h2>
        <DataState
          pending={history.isPending}
          error={history.error}
          retry={() => void history.refetch()}
        />
        {history.data && !messages.length && <p role="status">No recorded interactions.</p>}
        <ol className="grid gap-3">
          {messages.map((m) => (
            <li key={m.raw_message_id} className="rounded border p-4">
              <p className="font-medium">
                {m.channel} · {m.direction} ·{" "}
                {m.event_at
                  ? new Date(m.event_at).toLocaleString("en-PH", { timeZone: "Asia/Manila" })
                  : "Provider time unknown"}
              </p>
              <p>{m.excerpt ?? "No excerpt available"}</p>
              {m.topic && <p>Suggested topic: {m.topic}</p>}
              {m.derived_status_code && <p>Suggested status: {m.derived_status_code}</p>}
              {m.staff_email && <p>Reviewed by {m.staff_email}</p>}
              <details>
                <summary>Source evidence</summary>
                <p>Message: {m.source_message_id ?? m.raw_message_id}</p>
                <p>Account: {m.source_account_id ?? "Not supplied"}</p>
                <p>Raw record: {m.raw_message_id}</p>
              </details>
            </li>
          ))}
        </ol>
        {history.hasNextPage && (
          <Button
            variant="outline"
            disabled={history.isFetchingNextPage}
            onClick={() => void history.fetchNextPage()}
          >
            Load more history
          </Button>
        )}
      </section>
      {lead.data?.record_type === "inquiry" && (
        <ConfirmClinic row={lead.data} messages={messages} />
      )}
    </div>
  );
}
