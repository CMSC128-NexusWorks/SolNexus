import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";

/** Cached answer to "who is signed in": a StaffUser, or null when signed out. */
export const SESSION_QUERY_KEY = ["auth", "session"] as const;

export function createQueryClient() {
  // Any 401 means the session ended (expired, signed out elsewhere, password reset).
  // Clearing the cached user lets RequireAuth send staff back to sign-in.
  const onError = (error: Error) => {
    if (error instanceof ApiError && error.isUnauthorized) {
      client.setQueryData(SESSION_QUERY_KEY, null);
    }
  };

  const client = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // Retrying a 4xx (signed out, not found, validation) never helps.
        retry: (failureCount, error) =>
          !(error instanceof ApiError && error.status < 500) && failureCount < 2,
      },
    },
  });
  return client;
}
