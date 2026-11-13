import type { ReactNode } from "react";
import { Link, useLocation, useParams } from "react-router";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/api/client";
import type { ImportBatchState, ImportResult, ImportRowCandidate } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

import type { ImportResultState } from "./import-page";
import { basisLabel, reasonLabel, warningLabel } from "./labels";
import { useImportBatch } from "./queries";

const STATE_TEXT: Record<ImportBatchState, string> = {
  processing: "Still importing. This page updates by itself.",
  needs_review: "Imported. Some rows are held until staff decide whether they are the same clinic.",
  completed: "Import complete.",
  failed: "This upload failed and nothing was imported. Upload the file again to retry.",
};

/** SNX-62: what one upload did, from GET /imports/{batch_id}. Read-only; it decides nothing. */
export function ImportResultPage() {
  const { batchId = "" } = useParams();
  const location = useLocation();
  const replayed = (location.state as ImportResultState | null)?.replayed === true;
  const batch = useImportBatch(batchId);

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap gap-4">
        <Link className="underline" to="/">
          ← Back to leads
        </Link>
        <Link className="underline" to="/imports">
          Upload another workbook
        </Link>
      </div>
      <h1 className="text-3xl font-semibold">Import results</h1>
      {batch.isPending && <p role="status">Loading import results…</p>}
      {batch.error && <LoadError error={batch.error} retry={() => void batch.refetch()} />}
      {batch.data && <BatchResult batch={batch.data} replayed={replayed} />}
    </div>
  );
}

function LoadError({ error, retry }: { error: Error; retry: () => void }) {
  const location = useLocation();
  if (error instanceof ApiError && error.isUnauthorized)
    return (
      <p role="alert">
        Your session expired.{" "}
        <Link className="underline" to="/login" state={{ from: location }}>
          Sign in again
        </Link>
      </p>
    );
  if (error instanceof ApiError && error.status === 404)
    return <p role="alert">Import not found.</p>;
  return (
    <div role="alert">
      Couldn’t load the import results.{" "}
      <Button variant="outline" onClick={retry}>
        Retry
      </Button>
    </div>
  );
}

function BatchResult({ batch, replayed }: { batch: ImportResult; replayed: boolean }) {
  const rejected = batch.rows.filter((row) => row.result === "rejected");
  const held = batch.rows.filter((row) => row.result === "needs_review");
  const openReviews = batch.field_reviews.filter((review) => review.state === "unresolved");
  const counts = batch.counts;
  // review_group is the import_row_id of the group's first row, which means nothing to staff, so the
  // groups are numbered 1, 2, 3… in the order they first appear.
  const groupNumbers = new Map(
    [...new Set(held.map((row) => row.review_group).filter((g) => g !== null))].map((g, i) => [
      g,
      i + 1,
    ]),
  );

  // Warnings never block a row, so show how often each occurred rather than one line per row.
  const warningCounts = new Map<string, number>();
  for (const row of batch.rows)
    for (const code of row.warnings) warningCounts.set(code, (warningCounts.get(code) ?? 0) + 1);

  return (
    <>
      <p className="text-muted-foreground">
        {batch.original_filename} · uploaded {formatDateTime(batch.uploaded_at)}
      </p>
      {replayed && (
        <Alert role="status">
          <AlertTitle>This file was already imported</AlertTitle>
          <AlertDescription>
            These are the results of that earlier upload. No new clinics or duplicates were created.
          </AlertDescription>
        </Alert>
      )}
      <p role="status" className="font-medium">
        {STATE_TEXT[batch.state]}
      </p>

      <section aria-labelledby="summary-heading" className="grid gap-3">
        <h2 id="summary-heading" className="text-lg font-semibold">
          Summary
        </h2>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Count label="Clinics created" value={counts.created_clinics} />
          <Count label="Rows accepted" value={counts.accepted_rows} />
          <Count label="Rows held for review" value={counts.needs_review_rows} />
          <Count label="Rows rejected" value={counts.rejected_rows} />
          <Count label="Blank rows skipped" value={counts.skipped_rows} />
        </dl>
        {openReviews.length > 0 && (
          <p>
            {openReviews.length} field {openReviews.length === 1 ? "conflict" : "conflicts"} to
            resolve, where rows of the same clinic disagree on:{" "}
            {[...new Set(openReviews.map((review) => review.field_name))].join(", ")}.
          </p>
        )}
      </section>

      {held.length > 0 && (
        <section aria-labelledby="held-heading" className="grid gap-3">
          <h2 id="held-heading" className="text-lg font-semibold">
            Held for review ({held.length})
          </h2>
          <p className="text-sm text-muted-foreground">
            These rows may be the same clinic as another row or an existing clinic. Nothing was
            created or merged for them. Rows in the same group should be decided together.
          </p>
          <ResultTable headings={["Group", "Sheet", "Row", "Clinic name", "Possible match"]}>
            {held.map((row) => (
              <TableRow key={row.import_row_id}>
                <TableCell className="p-3">
                  {(row.review_group && groupNumbers.get(row.review_group)) ?? "—"}
                </TableCell>
                <TableCell className="p-3">{row.sheet}</TableCell>
                <TableCell className="p-3">{row.row}</TableCell>
                <TableCell className="p-3">{row.proposed_fields?.clinic_name ?? "—"}</TableCell>
                <TableCell className="p-3">
                  <ul className="grid gap-1">
                    {row.candidates.map((candidate, i) => (
                      <li key={i}>
                        <CandidateText candidate={candidate} />
                      </li>
                    ))}
                  </ul>
                </TableCell>
              </TableRow>
            ))}
          </ResultTable>
        </section>
      )}

      {rejected.length > 0 && (
        <section aria-labelledby="rejected-heading" className="grid gap-3">
          <h2 id="rejected-heading" className="text-lg font-semibold">
            Rejected rows ({rejected.length})
          </h2>
          <p className="text-sm text-muted-foreground">
            These rows were not imported. Fix them in the workbook and upload it again if they
            should be leads.
          </p>
          <ResultTable headings={["Sheet", "Row", "Reason"]}>
            {rejected.map((row) => (
              <TableRow key={row.import_row_id}>
                <TableCell className="p-3">{row.sheet}</TableCell>
                <TableCell className="p-3">{row.row}</TableCell>
                <TableCell className="p-3">{row.reasons.map(reasonLabel).join("; ")}</TableCell>
              </TableRow>
            ))}
          </ResultTable>
        </section>
      )}

      {warningCounts.size > 0 && (
        <section aria-labelledby="warnings-heading" className="grid gap-3">
          <h2 id="warnings-heading" className="text-lg font-semibold">
            Warnings
          </h2>
          <p className="text-sm text-muted-foreground">
            These rows were still imported or held; check the affected values on the dashboard.
          </p>
          <ul className="grid list-disc gap-1 pl-5">
            {[...warningCounts].map(([code, count]) => (
              <li key={code}>
                {warningLabel(code)}: {count} {count === 1 ? "row" : "rows"}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border p-3">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-2xl font-semibold">{value}</dd>
    </div>
  );
}

function ResultTable({ headings, children }: { headings: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-md border">
      <Table className="text-left text-sm">
        <TableHeader className="bg-muted">
          <TableRow>
            {headings.map((h) => (
              <TableHead scope="col" key={h} className="p-3">
                {h}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>{children}</TableBody>
      </Table>
    </div>
  );
}

/** A candidate is another upload row, or (once that row is accepted, or for a prior clinic) a clinic. */
function CandidateText({ candidate }: { candidate: ImportRowCandidate }) {
  const why = candidate.basis.map(basisLabel).join(", ");
  if (candidate.clinic_id)
    return (
      <>
        <Link className="underline" to={`/leads/${candidate.clinic_id}`}>
          {candidate.clinic_name ?? "Existing clinic"}
        </Link>{" "}
        ({why})
      </>
    );
  return (
    <>
      {candidate.sheet} row {candidate.row} ({why})
    </>
  );
}
