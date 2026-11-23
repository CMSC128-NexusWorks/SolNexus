import { Link, useLocation } from "react-router";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";

/** Shared announcements keep failure distinct from an empty result. */
export function DataState({
  pending,
  error,
  retry,
}: {
  pending: boolean;
  error: Error | null;
  retry: () => void;
}) {
  const location = useLocation();
  if (pending) return <p role="status">Loading leads…</p>;
  if (!error) return null;
  if (error instanceof ApiError && error.isUnauthorized)
    return (
      <p role="alert">
        Your session expired.{" "}
        <Link to="/login" state={{ from: location }}>
          Sign in again
        </Link>
      </p>
    );
  if (error instanceof ApiError && error.status === 404) return <p role="alert">Lead not found.</p>;
  return (
    <div role="alert">
      Couldn’t load data.{" "}
      <Button variant="outline" onClick={retry}>
        Retry
      </Button>
    </div>
  );
}
