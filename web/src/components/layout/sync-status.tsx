import { Badge } from "@/components/ui/badge";
import { usePipelineStatus } from "@/features/leads/queries";
import { formatRelative } from "@/lib/format";

/** "Synced 6 min ago" from the last successful silver publication. */
export function SyncStatus() {
  const { data, isError } = usePipelineStatus();

  if (isError) return <Badge variant="destructive">Sync status unavailable</Badge>;
  if (!data) return <Badge variant="secondary">Checking sync…</Badge>;
  if (!data.published_at) return <Badge variant="outline">Not synced yet</Badge>;

  // Expose the exact publication instant as well as relative age; a read or edit never advances it.
  return (
    <Badge
      variant="secondary"
      title={new Date(data.published_at).toLocaleString("en-PH", { timeZone: "Asia/Manila" })}
    >
      Synced {formatRelative(data.published_at)}
    </Badge>
  );
}
