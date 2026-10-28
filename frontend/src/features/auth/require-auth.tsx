import { Navigate, Outlet, useLocation } from "react-router";

import { Spinner } from "@/components/ui/spinner";

import { useAuth } from "./auth-provider";

/** Wraps protected routes. Signed-out users are sent to /login and returned afterwards. */
export function RequireAuth() {
  const { user, isChecking } = useAuth();
  const location = useLocation();

  if (isChecking) {
    return (
      <div className="flex min-h-svh items-center justify-center" aria-label="Checking sign-in">
        <Spinner />
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}
