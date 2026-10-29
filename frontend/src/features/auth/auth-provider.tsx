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
  /**
   * True when the session check failed for a reason other than "signed out" (network error, 5xx
   * after retries). The session may still be valid, so screens must not treat this as signed out.
   */
  isUnavailable: boolean;
  /** Ask the API again after isUnavailable. */
  recheckSession: () => void;
  signIn: (credentials: LoginRequest) => Promise<StaffUser>;
  /** Rejects, leaving the user signed in, when the API could not end the session. */
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

  // Only forget the user once the API has revoked the session. If logout fails (network error, 5xx),
  // the server session is still live, so showing "signed out" would be a lie: a reload would sign
  // the user straight back in, which matters on a shared machine. The error goes to the caller.
  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } catch (error) {
      // A 401 means there was no session to end, which is the outcome sign-out wants.
      if (!(error instanceof ApiError && error.isUnauthorized)) throw error;
    }
    clearSignedInData(queryClient);
  }, [queryClient]);

  const { refetch } = session;
  const recheckSession = useCallback(() => void refetch(), [refetch]);
  // A failed background refetch keeps the last answer (session.data), so only an error with no
  // answer at all counts as unavailable.
  const isUnavailable = session.isError && session.data === undefined;

  const value = useMemo(
    () => ({
      user: session.data ?? null,
      isChecking: session.isPending || (isUnavailable && session.isFetching),
      isUnavailable,
      recheckSession,
      signIn,
      signOut,
    }),
    [
      session.data,
      session.isPending,
      session.isFetching,
      isUnavailable,
      recheckSession,
      signIn,
      signOut,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
