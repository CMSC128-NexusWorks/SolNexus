import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { MOCK_CREDENTIALS } from "@/mocks/credentials";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

function fields() {
  return {
    email: screen.getByLabelText("Email"),
    password: screen.getByLabelText("Password"),
    submit: screen.getByRole("button", { name: "Sign in" }),
  };
}

async function renderLogin(path = "/login") {
  const result = renderApp(path, { user: null });
  await screen.findByRole("heading", { name: "Sign in" });
  return result;
}

describe("login page", () => {
  it("signs in with valid credentials and opens the dashboard", async () => {
    const { router } = await renderLogin();
    const { email, password, submit } = fields();

    await userEvent.type(email, MOCK_CREDENTIALS.email);
    await userEvent.type(password, MOCK_CREDENTIALS.password);
    await userEvent.click(submit);

    expect(
      await screen.findByRole("heading", { name: "Clinics to call today" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });

  it("returns staff to the page they originally asked for", async () => {
    const { router } = renderApp("/leads/clinic-0001", { user: null });
    await screen.findByRole("heading", { name: "Sign in" });

    await userEvent.type(fields().email, MOCK_CREDENTIALS.email);
    await userEvent.type(fields().password, MOCK_CREDENTIALS.password);
    await userEvent.click(fields().submit);

    await vi.waitFor(() => expect(router.state.location.pathname).toBe("/leads/clinic-0001"));
  });

  it("shows one generic error for wrong credentials, without saying which field was wrong", async () => {
    const { router } = await renderLogin();
    const { email, password, submit } = fields();

    await userEvent.type(email, MOCK_CREDENTIALS.email);
    await userEvent.type(password, "not-the-password");
    await userEvent.click(submit);

    expect(await screen.findByText("Email or password is incorrect.")).toBeInTheDocument();
    expect(email).toHaveValue(MOCK_CREDENTIALS.email);
    expect(password).toHaveValue("");
    expect(password).toHaveFocus();
    expect(email).not.toHaveAttribute("aria-invalid", "true");
    expect(router.state.location.pathname).toBe("/login");
  });

  it("asks for missing fields without calling the API", async () => {
    let loginCalls = 0;
    server.events.on("request:start", ({ request }) => {
      if (request.url.endsWith("/auth/login")) loginCalls += 1;
    });
    await renderLogin();

    await userEvent.click(fields().submit);

    expect(await screen.findByText("Enter your email.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(fields().email).toHaveAttribute("aria-invalid", "true");
    expect(fields().email).toHaveFocus();
    expect(loginCalls).toBe(0);
    server.events.removeAllListeners();
  });

  it("submits with the Enter key", async () => {
    const { router } = await renderLogin();

    await userEvent.type(fields().email, MOCK_CREDENTIALS.email);
    await userEvent.type(fields().password, `${MOCK_CREDENTIALS.password}{Enter}`);

    await vi.waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });

  it("disables the button while signing in", async () => {
    let release!: () => void;
    server.use(
      http.post("*/api/v1/auth/login", async () => {
        await new Promise<void>((resolve) => (release = resolve));
        return HttpResponse.json({ user_id: "u-1", email: MOCK_CREDENTIALS.email });
      }),
    );
    await renderLogin();

    await userEvent.type(fields().email, MOCK_CREDENTIALS.email);
    await userEvent.type(fields().password, MOCK_CREDENTIALS.password);
    await userEvent.click(fields().submit);

    const pending = await screen.findByRole("button", { name: "Signing in…" });
    expect(pending).toBeDisabled();
    release();
  });

  it("tells staff to try again when the API can't be reached", async () => {
    server.use(http.post("*/api/v1/auth/login", () => HttpResponse.error()));
    await renderLogin();

    await userEvent.type(fields().email, MOCK_CREDENTIALS.email);
    await userEvent.type(fields().password, MOCK_CREDENTIALS.password);
    await userEvent.click(fields().submit);

    expect(
      await screen.findByText("Couldn't reach SolNexus. Check your connection and try again."),
    ).toBeInTheDocument();
    expect(fields().password).toHaveValue(MOCK_CREDENTIALS.password);
  });

  it("has no sign-up link", async () => {
    await renderLogin();

    expect(screen.queryByRole("link", { name: /sign up|register|create account/i })).toBeNull();
    expect(screen.getByText(/accounts are created by the SolNexus team/i)).toBeInTheDocument();
  });
});
