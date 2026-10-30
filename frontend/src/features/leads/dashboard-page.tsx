import { useLeads, useDueLeads, useNeedsName } from "./queries";
import { Input } from "@/components/ui/input";
import { FieldSelect } from "./field-select";
import { PipelineWarning } from "./pipeline-warning";
import { useSearchParams } from "react-router";
import { STATUS_LABELS, type StatusCode } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { DataState } from "./data-state";
import { LeadTable } from "./lead-table";

/** Independent cursors keep search from hiding urgent work in the other tables. */
function LeadSection({
  title,
  mode,
  q,
  status,
}: {
  title: string;
  mode: "all" | "due" | "needs-name";
  q?: string;
  status?: StatusCode;
}) {
  const all = useLeads({ q, status }, mode === "all");
  const due = useDueLeads(mode === "due");
  const needs = useNeedsName(mode === "needs-name");
  const data = mode === "due" ? due : mode === "needs-name" ? needs : all;
  const rows = [
    ...new Map(data.data?.pages.flatMap((p) => p.items).map((r) => [r.lead_id, r])).values(),
  ];
  const heading = `heading-${mode}`;
  return (
    <section aria-labelledby={heading} className="grid gap-3">
      <h2 id={heading} className="text-lg font-semibold">
        {title}
      </h2>
      <DataState pending={data.isPending} error={data.error} retry={() => void data.refetch()} />
      {data.data && !data.error && (
        <LeadTable
          rows={rows}
          empty={
            mode === "due"
              ? "No leads due today."
              : mode === "needs-name"
                ? "No inquiries need a clinic name."
                : q || status
                  ? "No search results. Try clearing the filters."
                  : "No leads yet."
          }
        />
      )}
      {data.hasNextPage && (
        <Button
          variant="outline"
          disabled={data.isFetchingNextPage}
          onClick={() => void data.fetchNextPage()}
        >
          {data.isFetchingNextPage ? "Loading…" : `Load more ${title.toLowerCase()}`}
        </Button>
      )}
    </section>
  );
}

/** URL-owned filters survive detail navigation and refresh. */
export function DashboardPage() {
  const [params, setParams] = useSearchParams();
  function change(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }
  const status = params.get("status");
  return (
    <div className="flex flex-col gap-8">
      <header>
        <p className="text-sm text-muted-foreground">
          {new Date().toLocaleDateString("en-PH", { timeZone: "Asia/Manila", dateStyle: "full" })}
        </p>
        <h1 className="text-3xl font-semibold">Clinics to call today</h1>
      </header>
      <PipelineWarning />
      <LeadSection title="Due today" mode="due" />
      <LeadSection title="Needs clinic name" mode="needs-name" />
      <div className="grid gap-3 rounded border p-4 sm:grid-cols-3">
        <label className="grid gap-1 text-sm">
          Search clinic or contact
          <Input
            className="rounded border p-2"
            type="search"
            value={params.get("q") ?? ""}
            onChange={(e) => change("q", e.target.value)}
          />
        </label>
        <FieldSelect
          label="Status"
          value={status ?? ""}
          onChange={(value) => change("status", value)}
          options={[
            { value: "", label: "All statuses" },
            ...Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label })),
          ]}
        />
        <Button variant="outline" className="self-end" onClick={() => setParams({})}>
          Clear filters
        </Button>
      </div>
      <LeadSection
        title="All leads"
        mode="all"
        q={params.get("q") ?? undefined}
        status={
          status && Object.prototype.hasOwnProperty.call(STATUS_LABELS, status)
            ? (status as StatusCode)
            : undefined
        }
      />
    </div>
  );
}
