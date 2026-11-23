import { useId, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";

import { MAX_WORKBOOK_BYTES, uploadErrorMessage } from "./labels";
import { useWorkbookUpload } from "./queries";

/** Navigation state the result page reads; GET /imports/{id} itself does not say it was a replay. */
export interface ImportResultState {
  replayed?: boolean;
}

/**
 * Checks the browser can make before uploading. The API repeats them (it is the real boundary); these
 * only spare staff a 10 MB upload that is certain to be refused.
 */
function localProblem(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".xlsx"))
    return "Choose the lead workbook as an .xlsx file.";
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_WORKBOOK_BYTES) return "The workbook is larger than 10 MB.";
  return null;
}

/** SNX-62: upload the legacy lead workbook (FR-02) and go to its results. */
export function ImportPage() {
  const navigate = useNavigate();
  const upload = useWorkbookUpload();
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const inputId = useId();
  const hintId = useId();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file || upload.isPending) return;
    const local = localProblem(file);
    setProblem(local);
    if (local) return;
    upload.mutate(file, {
      onSuccess: ({ batch_id, replayed }) =>
        navigate(`/imports/${batch_id}`, { state: { replayed } satisfies ImportResultState }),
    });
  }

  const message = problem ?? (upload.error ? uploadErrorMessage(upload.error) : null);

  return (
    <div className="mx-auto grid max-w-2xl gap-6">
      <Link className="underline" to="/">
        ← Back to leads
      </Link>
      <Card>
        <CardHeader>
          <CardTitle>
            <h1 className="text-2xl font-semibold">Import lead workbook</h1>
          </CardTitle>
          <CardDescription>
            Upload SolTech&apos;s lead workbook to add its clinics to SolNexus. Rows that might be
            the same clinic as another row are held for staff review instead of being merged.
            Uploading the same file again creates nothing new.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form aria-label="Upload workbook" className="grid gap-4" onSubmit={handleSubmit}>
            <Field>
              <FieldLabel htmlFor={inputId}>Workbook file</FieldLabel>
              <Input
                id={inputId}
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                aria-describedby={hintId}
                disabled={upload.isPending}
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setProblem(null);
                  upload.reset();
                }}
              />
              <FieldDescription id={hintId}>.xlsx only, up to 10 MB.</FieldDescription>
            </Field>
            {message && (
              <Alert variant="destructive" role="alert">
                <AlertTitle>Nothing was imported</AlertTitle>
                <AlertDescription>{message}</AlertDescription>
              </Alert>
            )}
            <div>
              <Button type="submit" disabled={!file || upload.isPending}>
                {upload.isPending && <Spinner />}
                {upload.isPending ? "Importing…" : "Upload workbook"}
              </Button>
            </div>
            {upload.isPending && (
              <p role="status" className="text-sm text-muted-foreground">
                Importing the workbook. This usually takes a few seconds.
              </p>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
