import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { getSession } from "@/lib/api/auth";
import { MOCK_USER } from "@/mocks/data";
import { server } from "@/mocks/server";
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

describe("staff session", () => {
  it("asks the API who is signed in instead of remembering it in the browser", async () => {
    renderApp("/");

    expect(await screen.findByText(MOCK_USER.email)).toBeInTheDocument();
    expect(sessionStorage.getItem("solnexus.user")).toBeNull();
  });

  it("sends staff back to sign-in when the API says the session has ended", async () => {
    server.use(
      http.get("*/api/v1/leads/due", () =>
        HttpResponse.json(
          { error: { code: "unauthorized", message: "Sign in required", details: [] } },
          { status: 401 },
        ),
      ),
    );
    const { router } = renderApp("/");

    expect(await screen.findByText("Sign-in form")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });

  it("ends the session on the API when staff sign out", async () => {
    const { router } = renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByText("Sign-in form")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    await expect(getSession()).rejects.toMatchObject({ status: 401 });
  });

  it("says the API is unreachable, not signed out, when the session check fails", async () => {
    let apiDown = true;
    server.use(
      http.get("*/api/v1/auth/session", () =>
        apiDown
          ? HttpResponse.json(
              { error: { code: "internal_error", message: "Something went wrong", details: [] } },
              { status: 503 },
            )
          : undefined,
      ),
    );
    const { router } = renderApp("/");

    expect(await screen.findByText("Can't reach SolNexus right now")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");

    apiDown = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText(MOCK_USER.email)).toBeInTheDocument();
  });

  it("keeps staff signed in and says so when sign-out fails", async () => {
    server.use(
      http.post("*/api/v1/auth/logout", () =>
        HttpResponse.json(
          { error: { code: "internal_error", message: "Something went wrong", details: [] } },
          { status: 503 },
        ),
      ),
    );
    const { router } = renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByText(/Couldn't sign out/)).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
    expect(screen.getByText(MOCK_USER.email)).toBeInTheDocument();
  });
});
