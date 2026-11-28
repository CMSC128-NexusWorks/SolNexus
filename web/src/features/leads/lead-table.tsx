import { Fragment, useState } from "react";
import { Link, useLocation } from "react-router";
import { Button } from "@/components/ui/button";
import { STATUS_LABELS, type LeadRow } from "@/lib/api/types";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { RowEditor } from "./row-editor";

/** Links and buttons stay separate so keyboard navigation and editing never trigger each other. */
export function LeadTable({ rows, empty }: { rows: LeadRow[]; empty: string }) {
  const [editing, setEditing] = useState<string | null>(null);
  const location = useLocation();
  if (!rows.length)
    return (
      <p role="status" className="rounded border p-5 text-muted-foreground">
        {empty}
      </p>
    );
  return (
    <div className="overflow-x-auto rounded-md border">
      <Table className="min-w-[980px] text-left text-sm">
        <TableHeader className="bg-muted">
          <TableRow>
            {[
              "Clinic / contact",
              "Status",
              "Suggested topic",
              "Next step",
              "Next action",
              "Last contact",
              "Channel",
              "Actions",
            ].map((h) => (
              <TableHead scope="col" key={h} className="p-3">
                {h}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <Fragment key={row.lead_id}>
              <TableRow className="border-t align-top">
                <TableCell className="p-3">
                  <Link
                    className="font-medium underline underline-offset-4"
                    to={`/leads/${row.lead_id}`}
                    state={{ returnTo: location.pathname + location.search }}
                  >
                    {row.clinic_name ?? "Clinic name unknown"}
                  </Link>
                  <div>{row.contact_person}</div>
                  <div>{row.contact_number ?? "Phone unknown"}</div>
                  {row.email && <div>{row.email}</div>}
                  {row.pending_projection && <small>Staff changes pending sync</small>}
                </TableCell>
                <TableCell className="p-3">
                  {row.status_code ? STATUS_LABELS[row.status_code] : "Unknown"}
                </TableCell>
                <TableCell className="p-3">{row.latest_topic ?? "No suggested topic"}</TableCell>
                <TableCell className="p-3">{row.next_step ?? "—"}</TableCell>
                <TableCell className="p-3">{row.next_action_date ?? "Not scheduled"}</TableCell>
                <TableCell className="p-3">
                  {row.last_contact_at
                    ? new Date(row.last_contact_at).toLocaleString("en-PH", {
                        timeZone: "Asia/Manila",
                      })
                    : "No dated contact"}
                </TableCell>
                <TableCell className="p-3">{row.channels?.join(", ") || "—"}</TableCell>
                <TableCell className="p-3">
                  <Button variant="outline" onClick={() => setEditing(row.lead_id)}>
                    Edit row
                  </Button>
                  {row.record_type === "inquiry" && (
                    <div className="mt-2">
                      {row.email ? (
                        <a
                          className="underline"
                          href={`mailto:${encodeURIComponent(row.email)}?subject=Your%20clinic%20name&body=Could%20you%20please%20confirm%20your%20clinic%20name%3F`}
                        >
                          Email to ask
                        </a>
                      ) : (
                        <span>Add an email to ask</span>
                      )}
                      <br />
                      <Link
                        className="underline"
                        to={`/leads/${row.lead_id}`}
                        state={{ returnTo: location.pathname + location.search }}
                      >
                        Review reply and confirm
                      </Link>
                    </div>
                  )}
                </TableCell>
              </TableRow>
              {editing === row.lead_id && (
                <TableRow>
                  <TableCell colSpan={8}>
                    <RowEditor row={row} close={() => setEditing(null)} />
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
