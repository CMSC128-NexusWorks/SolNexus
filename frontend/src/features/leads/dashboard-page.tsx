import { TicketPlaceholder } from "@/components/ticket-placeholder";

import { useDueLeads, useLeads } from "./queries";

const today = new Intl.DateTimeFormat("en-GB", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "Asia/Manila",
});

// Landing screen (wireframe 02). Due today sits above All leads with no clicks needed (NFR-04).
export function DashboardPage() {
  const due = useDueLeads();
  const leads = useLeads();

  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-1">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {today.format(new Date())}
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Clinics to call today</h1>
      </header>

      <section aria-labelledby="due-today" className="flex flex-col gap-4">
        <h2 id="due-today" className="text-lg font-semibold">
          Due today
        </h2>
        {/* TODO(SNX-57): replace with the Due today table. Loading/empty/error states: SNX-60. */}
        <TicketPlaceholder
          ticket="SNX-57"
          title="Due today table"
          wireframe="02 · Dashboard — default view (FR-07 + FR-08).png"
        >
          <p className="text-sm text-muted-foreground">
            {due.data
              ? `${due.data.items.length} due rows loaded from the API`
              : "Loading due rows…"}
          </p>
        </TicketPlaceholder>
      </section>

      <section aria-labelledby="all-leads" className="flex flex-col gap-4">
        <h2 id="all-leads" className="text-lg font-semibold">
          All clinics
        </h2>
        {/* TODO(SNX-57): replace with the All leads table. Search and status filter: SNX-58. */}
        <TicketPlaceholder
          ticket="SNX-57 · SNX-58"
          title="All leads table with search and status filter"
          wireframe="03 · All Leads — filtered (FR-09).png"
        >
          <p className="text-sm text-muted-foreground">
            {leads.data ? `${leads.data.items.length} leads loaded from the API` : "Loading leads…"}
          </p>
        </TicketPlaceholder>
      </section>
    </div>
  );
}
