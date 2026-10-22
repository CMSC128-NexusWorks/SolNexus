import { useState } from "react";
import { Navigate, useLocation, useNavigate, type Location } from "react-router";

import { TicketPlaceholder } from "@/components/ticket-placeholder";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { MOCK_CREDENTIALS } from "@/mocks/credentials";

import { useAuth } from "./auth-provider";

// TODO(SNX-56): replace this page with the real sign-in form from wireframe 01.
export function LoginPage() {
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [pending, setPending] = useState(false);
  const from = (location.state as { from?: Location } | null)?.from?.pathname ?? "/";

  if (user) return <Navigate to={from} replace />;

  async function continueWithMockAccount() {
    setPending(true);
    try {
      await signIn(MOCK_CREDENTIALS);
      navigate(from, { replace: true });
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <div className="w-full max-w-md">
        <TicketPlaceholder ticket="SNX-56" title="Sign-in form" wireframe="01 · Login (FR-10).png">
          {import.meta.env.VITE_USE_MOCKS === "true" && (
            <Button onClick={continueWithMockAccount} disabled={pending}>
              {pending && <Spinner data-icon="inline-start" />}
              Continue with mock account
            </Button>
          )}
        </TicketPlaceholder>
      </div>
    </main>
  );
}
