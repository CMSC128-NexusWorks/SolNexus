import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getImport, uploadWorkbook } from "@/lib/api/imports";
import { leadKeys } from "@/features/leads/queries";

export const importKeys = {
  batch: (batchId: string) => ["imports", batchId] as const,
};

/** One import batch. Polls only while the server still reports it as processing. */
export function useImportBatch(batchId: string) {
  return useQuery({
    queryKey: importKeys.batch(batchId),
    queryFn: () => getImport(batchId),
    enabled: Boolean(batchId),
    refetchInterval: (query) => (query.state.data?.state === "processing" ? 2_000 : false),
  });
}

export function useWorkbookUpload() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: uploadWorkbook,
    // An upload can create clinics, so the dashboard tables must not keep serving the old list.
    onSuccess: () => client.invalidateQueries({ queryKey: leadKeys.all }),
  });
}
