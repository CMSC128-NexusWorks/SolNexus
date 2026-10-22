import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import * as authApi from "@/lib/api/auth";
import type { LoginRequest, StaffUser } from "@/lib/api/types";

interface AuthContextValue {
  user: StaffUser | null;
  signIn: (credentials: LoginRequest) => Promise<StaffUser>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// TODO(SNX-27): the session itself is an HttpOnly cookie the browser can't read.
// The contract has no "who am I" endpoint yet, so we remember the signed-in user
// for this tab only. Replace this with a session check once SNX-27 defines one.
const STORAGE_KEY = "solnexus.user";

function readStoredUser(): StaffUser | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StaffUser) : null;
  } catch {
    return null;
  }
}

function storeUser(user: StaffUser | null) {
  try {
    if (user) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage can be unavailable (private mode); the in-memory state still works.
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<StaffUser | null>(readStoredUser);

  const signIn = useCallback(async (credentials: LoginRequest) => {
    const signedIn = await authApi.login(credentials);
    storeUser(signedIn);
    setUser(signedIn);
    return signedIn;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      storeUser(null);
      setUser(null);
    }
  }, []);

  const value = useMemo(() => ({ user, signIn, signOut }), [user, signIn, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
