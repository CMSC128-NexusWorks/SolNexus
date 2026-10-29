import { useRef, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate, type Location } from "react-router";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { ApiError } from "@/lib/api/client";
import { MOCK_CREDENTIALS } from "@/mocks/credentials";

import { useAuth } from "./auth-provider";

interface MissingFields {
  email?: string;
  password?: string;
}

/** Sign-in screen from wireframe 01 (FR-10). There is no sign-up: the team creates accounts. */
export function LoginPage() {
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  // Keep the query and hash too, so a filtered list or a lead's tab survives the trip through sign-in.
  const fromLocation = (location.state as { from?: Location } | null)?.from;
  const from = fromLocation
    ? `${fromLocation.pathname}${fromLocation.search}${fromLocation.hash}`
    : "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [missing, setMissing] = useState<MissingFields>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  if (user) return <Navigate to={from} replace />;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedEmail = email.trim();
    const nextMissing: MissingFields = {
      email: trimmedEmail ? undefined : "Enter your email.",
      password: password ? undefined : "Enter your password.",
    };
    setMissing(nextMissing);
    setFormError(null);
    if (nextMissing.email || nextMissing.password) {
      (nextMissing.email ? emailRef : passwordRef).current?.focus();
      return;
    }

    setPending(true);
    try {
      await signIn({ email: trimmedEmail, password });
      navigate(from, { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.isUnauthorized) {
        // The API answers the same for an unknown email, a wrong password or a deactivated
        // account, so the form can't and shouldn't point at a field.
        setFormError("Email or password is incorrect.");
        setPassword("");
        passwordRef.current?.focus();
      } else {
        // Network failure or server error: the credentials may be fine, so keep them for a retry.
        setFormError("Couldn't reach SolNexus. Check your connection and try again.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <div className="flex items-center gap-3 font-semibold">
          <span aria-hidden className="size-9 rounded-sm bg-muted-foreground/30" />
          SolNexus
        </div>
        <div className="flex flex-col gap-1">
          <h1 className="text-3xl font-semibold tracking-tight">Sign in</h1>
          <p className="text-sm text-muted-foreground">Lead tracking for the SolTech sales team</p>
        </div>

        {import.meta.env.VITE_USE_MOCKS === "true" && (
          // role="note": this is a hint, not an error, so screen readers shouldn't announce it.
          <Alert role="note">
            <AlertDescription>
              Mock API: sign in with {MOCK_CREDENTIALS.email} / {MOCK_CREDENTIALS.password}
            </AlertDescription>
          </Alert>
        )}

        {/* noValidate: show our own messages instead of the browser's, which vary by browser. */}
        <form noValidate onSubmit={handleSubmit}>
          <FieldGroup>
            {formError && (
              <Alert variant="destructive">
                <AlertDescription>{formError}</AlertDescription>
              </Alert>
            )}
            <Field data-invalid={!!missing.email || undefined}>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input
                ref={emailRef}
                id="email"
                type="email"
                autoComplete="username"
                placeholder="name@example.test"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                aria-invalid={!!missing.email || undefined}
                aria-describedby={missing.email ? "email-error" : undefined}
              />
              <FieldError id="email-error">{missing.email}</FieldError>
            </Field>
            <Field data-invalid={!!missing.password || undefined}>
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <Input
                ref={passwordRef}
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-invalid={!!missing.password || undefined}
                aria-describedby={missing.password ? "password-error" : undefined}
              />
              <FieldError id="password-error">{missing.password}</FieldError>
            </Field>
            <Button type="submit" size="lg" disabled={pending}>
              {/* aria-hidden: the label already says "Signing in…"; the spinner's own "Loading" would repeat it. */}
              {pending && <Spinner data-icon="inline-start" aria-hidden />}
              {pending ? "Signing in…" : "Sign in"}
            </Button>
          </FieldGroup>
        </form>

        <p className="text-sm text-muted-foreground">
          Accounts are created by the SolNexus team. Ask them if you need access.
        </p>
      </div>
    </main>
  );
}
