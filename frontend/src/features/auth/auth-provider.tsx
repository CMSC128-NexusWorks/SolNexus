import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import * as authApi from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import type { LoginRequest, StaffUser } from "@/lib/api/types";
import { clearSignedInData, SESSION_QUERY_KEY } from "@/lib/query-client";

interface AuthContextValue {
  user: StaffUser | null;
  /** True until the API has answered whether a session exists. */
  isChecking: boolean;
  signIn: (credentials: LoginRequest) => Promise<StaffUser>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// The session is an HttpOnly cookie the browser can't read, so the API is the only source of truth.
async function fetchSessionUser(): Promise<StaffUser | null> {
  try {
    return await authApi.getSession();
  } catch (error) {
    if (error instanceof ApiError && error.isUnauthorized) return null;
    throw error;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const session = useQuery({ queryKey: SESSION_QUERY_KEY, queryFn: fetchSessionUser });

  const signIn = useCallback(
    async (credentials: LoginRequest) => {
      const signedIn = await authApi.login(credentials);
      queryClient.setQueryData(SESSION_QUERY_KEY, signedIn);
      return signedIn;
    },
    [queryClient],
  );

  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      clearSignedInData(queryClient);
    }
  }, [queryClient]);

  const value = useMemo(
    () => ({ user: session.data ?? null, isChecking: session.isPending, signIn, signOut }),
    [session.data, session.isPending, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
