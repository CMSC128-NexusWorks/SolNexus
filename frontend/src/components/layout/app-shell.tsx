import { Link, Outlet, useNavigate } from "react-router";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";

import { SyncStatus } from "./sync-status";

/** Top bar shared by every signed-in screen (wireframes 02–08). */
export function AppShell() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const initials = user?.email.slice(0, 2).toUpperCase() ?? "?";

  async function handleSignOut() {
    await signOut();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b bg-muted/40">
        <div className="mx-auto grid h-16 max-w-7xl grid-cols-[1fr_auto_1fr] items-center gap-4 px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-3 font-semibold">
            <span aria-hidden className="size-7 rounded-sm bg-muted-foreground/30" />
            SolNexus
          </Link>
          <SyncStatus />
          <div className="flex items-center justify-end gap-2">
            <span className="hidden text-sm text-muted-foreground sm:inline">{user?.email}</span>
            <Button variant="ghost" size="sm" onClick={handleSignOut}>
              Sign out
            </Button>
            <Avatar>
              <AvatarFallback>{initials}</AvatarFallback>
            </Avatar>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
