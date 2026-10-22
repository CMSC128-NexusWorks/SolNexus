import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderApp } from "@/test/render";

describe("app routing", () => {
  it("sends signed-out users to the login page", async () => {
    const { router } = renderApp("/", { user: null });

    expect(await screen.findByText("Sign-in form")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });

  it("shows the dashboard with data from the mock API when signed in", async () => {
    renderApp("/");

    expect(
      await screen.findByRole("heading", { name: "Clinics to call today" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("3 due rows loaded from the API")).toBeInTheDocument();
    expect(await screen.findByText("7 leads loaded from the API")).toBeInTheDocument();
  });

  it("shows the sync status in the top bar", async () => {
    renderApp("/");

    expect(await screen.findByText(/^Synced /)).toBeInTheDocument();
  });
});
