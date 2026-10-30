import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/features/auth/auth-provider";
import { createQueryClient } from "@/lib/query-client";
import { MockScenarioControl } from "@/mocks/scenario-control";

export function AppProviders({
  children,
  queryClient,
}: {
  children: ReactNode;
  queryClient?: QueryClient;
}) {
  const [client] = useState(() => queryClient ?? createQueryClient());

  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        {children}
        <Toaster />
      </AuthProvider>
      {import.meta.env.VITE_USE_MOCKS === "true" && <MockScenarioControl />}
    </QueryClientProvider>
  );
}
