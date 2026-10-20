import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";

import { AppProviders } from "@/app/providers";
import { routes } from "@/app/router";
import type { StaffUser } from "@/lib/api/types";
import { createQueryClient } from "@/lib/query-client";
import { MOCK_USER } from "@/mocks/data";

interface RenderAppOptions {
  /** Start already signed in (default) or signed out. */
  user?: StaffUser | null;
}

/** Renders the real app at `path` with fresh providers. Use it for page-level tests. */
export function renderApp(path = "/", { user = MOCK_USER }: RenderAppOptions = {}) {
  if (user) sessionStorage.setItem("solnexus.user", JSON.stringify(user));
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });

  return {
    router,
    ...render(
      <AppProviders queryClient={queryClient}>
        <RouterProvider router={router} />
      </AppProviders>,
    ),
  };
}
