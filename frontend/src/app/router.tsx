import { createBrowserRouter } from "react-router";

import { AppShell } from "@/components/layout/app-shell";
import { LoginPage } from "@/features/auth/login-page";
import { RequireAuth } from "@/features/auth/require-auth";
import { DashboardPage } from "@/features/leads/dashboard-page";
import { LeadDetailPage } from "@/features/leads/lead-detail-page";

import { NotFoundPage } from "./not-found-page";

// Add new screens here. Everything under RequireAuth needs a signed-in staff user.
export const routes = [
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "leads/:clinicId", element: <LeadDetailPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
