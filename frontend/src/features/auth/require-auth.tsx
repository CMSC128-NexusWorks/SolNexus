import { Navigate, Outlet, useLocation } from "react-router";

import { useAuth } from "./auth-provider";

/** Wraps protected routes. Signed-out users are sent to /login and returned afterwards. */
export function RequireAuth() {
  const { user } = useAuth();
  const location = useLocation();

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}
