import { useMutation } from "@tanstack/react-query";
import { DownloadIcon } from "lucide-react";
import { useId } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { ApiError } from "@/lib/api/client";
import { downloadLeadsExport } from "@/lib/api/leads";
import { exportFilename, saveFile } from "@/lib/download";

/**
 * FR-19 "Download leads" (SNX-63). The dashboard already sits behind sign-in, and the API checks the
 * session again, so only signed-in staff can reach the button or the file.
 *
 * A mutation rather than a query: each click is a fresh snapshot that must not be cached or retried.
 * Being a mutation also routes a 401 through the global MutationCache handler, which clears the
 * cached leads and sends staff to sign-in; the toast explains why, since this page is then gone.
 */
export function DownloadLeadsButton() {
  const hintId = useId();
  const download = useMutation({
    mutationFn: downloadLeadsExport,
    onSuccess: (blob) => saveFile(blob, exportFilename(blob.type)),
    onError: (error) => {
      if (error instanceof ApiError && error.isUnauthorized)
        toast.error("Your session expired. Sign in again, then download the leads.");
    },
  });
  const failed =
    download.isError && !(download.error instanceof ApiError && download.error.isUnauthorized);

  return (
    <div className="flex flex-col items-end gap-1 text-right">
      <Button
        variant="outline"
        aria-describedby={hintId}
        disabled={download.isPending}
        onClick={() => download.mutate()}
      >
        {download.isPending ? <Spinner aria-hidden /> : <DownloadIcon aria-hidden />}
        {download.isPending ? "Preparing download…" : "Download leads"}
      </Button>
      {/* Sits next to the search and status filter, so say plainly that they don't apply. */}
      <p id={hintId} className="text-xs text-muted-foreground">
        Spreadsheet of every current lead, ignoring search and filters.
      </p>
      {failed && (
        <p role="alert" className="text-sm text-destructive">
          Couldn't download the leads. Check your connection and try again.
        </p>
      )}
    </div>
  );
}
