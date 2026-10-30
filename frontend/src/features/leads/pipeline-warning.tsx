import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { usePipelineStatus } from "./queries";

/** Failures and aged snapshots keep the last good data visible while making its limits explicit. */
export function PipelineWarning() {
  const pipeline = usePipelineStatus();
  if (pipeline.error)
    return (
      <Alert>
        <AlertTitle>Pipeline status unavailable</AlertTitle>
        <AlertDescription>
          Data freshness could not be checked.{" "}
          <Button variant="outline" onClick={() => void pipeline.refetch()}>
            Retry pipeline status
          </Button>
        </AlertDescription>
      </Alert>
    );
  const data = pipeline.data;
  if (!data) return null;
  const failed = data.pipelines.some(
    (row) => row.last_run_status === "failed" || row.last_run_status === "retrying",
  );
  if (!failed && !data.is_stale && data.published_at) return null;
  return (
    <Alert>
      <AlertTitle>
        {failed
          ? "A pipeline run failed"
          : data.is_stale
            ? "Lead data may be stale"
            : "No successful publication yet"}
      </AlertTitle>
      <AlertDescription>
        {failed
          ? "Showing the last successful publication. New messages or edits may still be pending."
          : data.is_stale
            ? `The last published snapshot is older than ${data.stale_after_minutes} minutes. Staff edits remain visible; new messages may be pending.`
            : "A successful Airflow publication is required before pipeline freshness can be confirmed."}
      </AlertDescription>
    </Alert>
  );
}
