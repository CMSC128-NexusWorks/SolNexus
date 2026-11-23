import { Navigate, Outlet, useLocation } from "react-router";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

import { useAuth } from "./auth-provider";

/** Wraps protected routes. Signed-out users are sent to /login and returned afterwards. */
export function RequireAuth() {
  const { user, isChecking, isUnavailable, recheckSession } = useAuth();
  const location = useLocation();

  if (isChecking) {
    return (
      <div className="flex min-h-svh items-center justify-center" aria-label="Checking sign-in">
        <Spinner />
      </div>
    );
  }
  if (isUnavailable) {
    // Not the sign-in page: the API never said the session ended, so it may still be valid.
    // Layout follows wireframe 08's states: heading, one line of explanation, one action.
    return (
      <div className="flex min-h-svh flex-col items-center justify-center gap-2 px-4 text-center">
        <h1 className="font-semibold">Can't reach SolNexus right now</h1>
        <p className="text-sm text-muted-foreground">
          You may still be signed in. Check your connection, then try again.
        </p>
        <Button variant="outline" className="mt-2" onClick={recheckSession}>
          Try again
        </Button>
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}
