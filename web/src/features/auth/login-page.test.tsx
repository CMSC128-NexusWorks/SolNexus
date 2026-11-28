import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SESSION_QUERY_KEY } from "@/lib/query-client";
import { MOCK_CREDENTIALS } from "@/mocks/credentials";
import { MOCK_USER } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";
import { setMockSession } from "@/mocks/handlers";

function fields() {
  return {
    email: screen.getByLabelText("Email"),
    password: screen.getByLabelText("Password"),
    submit: screen.getByRole("button", { name: "Sign in" }),
  };
}

type RequestStartListener = Parameters<typeof server.events.on<"request:start">>[1];
let requestListener: RequestStartListener | null = null;

/** Watch requests for one test. Only this listener is removed afterwards, not every listener. */
function watchRequests(listener: RequestStartListener) {
  requestListener = listener;
  server.events.on("request:start", listener);
}

async function renderLogin(path = "/login") {
  const result = renderApp(path, { user: null });
  await screen.findByRole("heading", { name: "Sign in" });
  return result;
}

describe("login page", () => {
  // Cleanup lives here, not at the end of a test, so it still runs when a test fails.
  afterEach(() => {
    vi.unstubAllEnvs();
    if (requestListener) server.events.removeListener("request:start", requestListener);
    requestListener = null;
  });

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

  it("returns staff to the page they originally asked for, query and hash included", async () => {
    const { router } = renderApp("/leads/clinic-0001?tab=history#latest", { user: null });
    await screen.findByRole("heading", { name: "Sign in" });

    await userEvent.type(fields().email, MOCK_CREDENTIALS.email);
    await userEvent.type(fields().password, MOCK_CREDENTIALS.password);
    await userEvent.click(fields().submit);

    await vi.waitFor(() => {
      const { pathname, search, hash } = router.state.location;
      expect(`${pathname}${search}${hash}`).toBe("/leads/clinic-0001?tab=history#latest");
    });
  });

  it("stays signed in when an older session check answers 401 after sign-in", async () => {
    const { router, queryClient } = await renderLogin();
    let answerOldCheck!: () => void;
    server.use(
      http.get("*/api/v1/auth/session", async () => {
        await new Promise<void>((resolve) => (answerOldCheck = resolve));
        return HttpResponse.json(
          { error: { code: "unauthorized", message: "Sign in required", details: [] } },
          { status: 401 },
        );
      }),
    );
    // A session check that left before the cookie existed, e.g. a refetch on window focus.
    void queryClient.refetchQueries({ queryKey: SESSION_QUERY_KEY });
    await vi.waitFor(() => expect(answerOldCheck).toBeDefined());

    await userEvent.type(fields().email, MOCK_CREDENTIALS.email);
    await userEvent.type(fields().password, MOCK_CREDENTIALS.password);
    await userEvent.click(fields().submit);
    await vi.waitFor(() => expect(router.state.location.pathname).toBe("/"));
    answerOldCheck();

    expect(
      await screen.findByRole("heading", { name: "Clinics to call today" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
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
    watchRequests(({ request }) => {
      if (request.url.endsWith("/auth/login")) loginCalls += 1;
    });
    await renderLogin();

    await userEvent.click(fields().submit);

    expect(await screen.findByText("Enter your email.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(fields().email).toHaveAttribute("aria-invalid", "true");
    expect(fields().email).toHaveFocus();
    expect(loginCalls).toBe(0);
  });

  it("clears a field's error as soon as staff type into it", async () => {
    await renderLogin();
    await userEvent.click(fields().submit);
    expect(await screen.findByText("Enter your email.")).toBeInTheDocument();

    await userEvent.type(fields().email, "s");

    expect(screen.queryByText("Enter your email.")).toBeNull();
    expect(fields().email).not.toHaveAttribute("aria-invalid");
    // The other field's message stays until that field is fixed.
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
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
        setMockSession(MOCK_USER);
        return HttpResponse.json({ user_id: "u-1", email: MOCK_CREDENTIALS.email });
      }),
    );
    const { router } = await renderLogin();

    await userEvent.type(fields().email, MOCK_CREDENTIALS.email);
    await userEvent.type(fields().password, MOCK_CREDENTIALS.password);
    await userEvent.click(fields().submit);

    const pending = await screen.findByRole("button", { name: "Signing in…" });
    expect(pending).toBeDisabled();
    release();
    // Let the sign-in finish inside this test, so its state updates don't land after cleanup.
    await vi.waitFor(() => expect(router.state.location.pathname).toBe("/"));
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

  it.each([
    [503, "SolNexus is having trouble right now. Try again in a few minutes."],
    [422, "Something went wrong signing in. Try again."],
  ])("explains a %i response without blaming the connection", async (status, message) => {
    server.use(
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json(
          { error: { code: "server_error", message: "Failed", details: [] } },
          { status },
        ),
      ),
    );
    await renderLogin();

    await userEvent.type(fields().email, MOCK_CREDENTIALS.email);
    await userEvent.type(fields().password, MOCK_CREDENTIALS.password);
    await userEvent.click(fields().submit);

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(fields().password).toHaveValue(MOCK_CREDENTIALS.password);
  });

  it("shows a spinner, not the form, while checking an existing session", async () => {
    let answerCheck!: () => void;
    server.use(
      http.get("*/api/v1/auth/session", async () => {
        await new Promise<void>((resolve) => (answerCheck = resolve));
        return HttpResponse.json(MOCK_USER);
      }),
    );
    const { router } = renderApp("/login", { user: MOCK_USER });

    expect(await screen.findByLabelText("Checking sign-in")).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).toBeNull();
    await vi.waitFor(() => expect(answerCheck).toBeDefined());
    answerCheck();

    await vi.waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });

  it("never prints the mock password outside the dev server", async () => {
    vi.stubEnv("VITE_USE_MOCKS", "true");
    vi.stubEnv("DEV", false);
    await renderLogin();

    expect(screen.queryByText(new RegExp(MOCK_CREDENTIALS.password))).toBeNull();
  });

  it("has no sign-up link", async () => {
    await renderLogin();

    expect(screen.queryByRole("link", { name: /sign up|register|create account/i })).toBeNull();
    expect(screen.getByText(/accounts are created by the SolNexus team/i)).toBeInTheDocument();
  });
});
