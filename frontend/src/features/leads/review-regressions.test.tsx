import { screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { renderApp } from "@/test/render";
import { setMockScenario } from "@/mocks/scenarios";
import { MOCK_LEADS } from "@/mocks/data";
import { getPipelineStatus, getLeads, updateLead } from "@/lib/api/leads";
import { setMockSession } from "@/mocks/handlers";
import { MOCK_USER } from "@/mocks/data";

/** These tests follow visible outcomes, including the mock controls' real HTTP failure responses. */
describe("review regressions", () => {
  it("keeps mock list and pipeline publication timestamps consistent across reads", async () => {
    setMockSession(MOCK_USER);
    setMockScenario("pipeline-stale");
    const before = await getPipelineStatus();
    const page = await getLeads();
    const after = await getPipelineStatus();
    expect(page.published_at).toBe(before.published_at);
    expect(after.published_at).toBe(before.published_at);
  });
  it("can trigger the loading scenario and then show its synthetic data", async () => {
    setMockScenario("loading");
    renderApp();
    expect((await screen.findAllByText("Loading leads…")).length).toBeGreaterThan(0);
    expect(
      (await screen.findAllByRole("link", { name: "Harborview Clinic" }, { timeout: 5000 })).length,
    ).toBeGreaterThan(0);
  });
  it("can trigger no-search-results without hiding the due list", async () => {
    setMockScenario("no-results");
    renderApp("/?q=Harborview");
    expect(await screen.findByText(/No search results/)).toBeInTheDocument();
    const due = screen.getByRole("region", { name: "Due today" });
    expect(await within(due).findByRole("link", { name: "Harborview Clinic" })).toBeInTheDocument();
  });
  it("retains a rejected email draft and associates its field error with the input", async () => {
    renderApp("/?q=Seaside");
    const all = await screen.findByRole("region", { name: "All leads" });
    await userEvent.click(await within(all).findByRole("button", { name: "Edit row" }));
    const form = screen.getByRole("form", { name: "Edit Seaside Dental & Medical" });
    const email = within(form).getByLabelText("Email");
    await userEvent.type(email, "not-an-email");
    await userEvent.click(within(form).getByRole("button", { name: "Save row" }));
    await waitFor(() => expect(email).toHaveAttribute("aria-invalid", "true"));
    expect(email).toHaveValue("not-an-email");
    expect(email).toHaveAccessibleDescription("Enter a valid email address");
    expect(MOCK_LEADS.find((r) => r.clinic_name === "Seaside Dental & Medical")?.email).toBeNull();
  });
  it("rejects inquiry geography/name patches with the same codes as the backend", async () => {
    setMockSession(MOCK_USER);
    const row = MOCK_LEADS.find((r) => r.record_type === "inquiry")!;
    await expect(updateLead(row, { region: "Not allowed" }, "")).rejects.toMatchObject({
      status: 422,
      code: "validation_error",
    });
    await expect(updateLead(row, { clinic_name: "Guessed" }, "")).rejects.toMatchObject({
      status: 422,
      code: "confirmation_evidence_required",
    });
    expect(row.version).toBe(1);
    expect(row.region).toBeUndefined();
  });
  it("reads pipeline status and warns about failed runs while retaining the last good leads", async () => {
    setMockScenario("pipeline-failed");
    renderApp();
    expect(await screen.findByText("A pipeline run failed")).toBeInTheDocument();
    expect(
      (await screen.findAllByRole("link", { name: "Harborview Clinic" })).length,
    ).toBeGreaterThan(0);
    expect((await getPipelineStatus()).last_run_status).toBe("failed");
  });
  it("warns when the pipeline snapshot is stale", async () => {
    setMockScenario("pipeline-stale");
    renderApp();
    expect(await screen.findByText("Lead data may be stale")).toBeInTheDocument();
  });
  it("triggers an empty due state without hiding All leads", async () => {
    setMockScenario("empty-due");
    renderApp();
    expect(await screen.findByText("No leads due today.")).toBeInTheDocument();
    expect((await screen.findAllByRole("link", { name: "Harborview Clinic" })).length).toBe(1);
  });
  it("triggers API failure with recovery controls", async () => {
    setMockScenario("api-error");
    renderApp();
    expect((await screen.findAllByText(/Couldn’t load data/)).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Retry" }).length).toBeGreaterThan(0);
  });
  it("triggers an expired session and keeps private leads off the page", async () => {
    setMockScenario("session-expired");
    const { router } = renderApp();
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(screen.queryByRole("link", { name: "Harborview Clinic" })).toBeNull();
  });
  it("renders actual interaction topic separately from the operational next step", async () => {
    MOCK_LEADS[0].latest_topic = "Synthetic pricing topic";
    renderApp("/?q=Harborview");
    const all = await screen.findByRole("region", { name: "All leads" });
    expect(await within(all).findByText("Synthetic pricing topic")).toBeInTheDocument();
    expect(within(all).getByText("Follow-up call agreed")).toBeInTheDocument();
    expect(screen.queryByLabelText("Next-action date")).toBeNull();
  });
});
