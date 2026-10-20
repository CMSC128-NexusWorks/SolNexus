import { Badge } from "@/components/ui/badge";
import { useDueLeads } from "@/features/leads/queries";
import { formatRelative } from "@/lib/format";

/** "Synced 6 min ago" from the last successful silver publication. */
export function SyncStatus() {
  const { data, isError } = useDueLeads();

  if (isError) return <Badge variant="destructive">Sync status unavailable</Badge>;
  if (!data) return <Badge variant="secondary">Checking sync…</Badge>;
  if (!data.published_at) return <Badge variant="outline">Not synced yet</Badge>;

  return <Badge variant="secondary">Synced {formatRelative(data.published_at)}</Badge>;
}
