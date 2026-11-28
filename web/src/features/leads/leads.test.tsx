import { screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderApp } from "@/test/render";
import { server } from "@/mocks/server";

/** Exercise user outcomes across the real router, query cache and HTTP client. */
describe("SNX-31 leads", () => {
  it("filters All leads without hiding Due today and retains filters after detail", async () => {
    const { router } = renderApp("/?status=awaiting_demo");
    const all = await screen.findByRole("region", { name: "All leads" });
    await within(all).findByRole("link", { name: "Lakeside Diagnostics" });
    expect(within(all).queryByRole("link", { name: "Harborview Clinic" })).toBeNull();
    const due = screen.getByRole("region", { name: "Due today" });
    expect(await within(due).findByRole("link", { name: "Harborview Clinic" })).toBeInTheDocument();
    await userEvent.click(within(all).getByRole("link", { name: "Lakeside Diagnostics" }));
    expect(await screen.findByText("Interaction history")).toBeInTheDocument();
    expect(await screen.findByText(/Thanks for the proposal/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: /Back to leads/ }));
    await waitFor(() => expect(router.state.location.search).toBe("?status=awaiting_demo"));
  });

  it("cancels a draft and saves a row through the shared API client", async () => {
    renderApp("/?q=Seaside");
    const all = await screen.findByRole("region", { name: "All leads" });
    await userEvent.click(await within(all).findByRole("button", { name: "Edit row" }));
    const form = screen.getByRole("form", { name: "Edit Seaside Dental & Medical" });
    await userEvent.type(within(form).getByLabelText("Contact person"), "Draft Person");
    await userEvent.click(within(form).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Draft Person")).toBeNull();
    await userEvent.click(within(all).getByRole("button", { name: "Edit row" }));
    const second = screen.getByRole("form", { name: "Edit Seaside Dental & Medical" });
    await userEvent.type(within(second).getByLabelText("Contact person"), "Saved Person");
    await userEvent.click(within(second).getByRole("button", { name: "Save row" }));
    expect(await within(all).findByText("Saved Person")).toBeInTheDocument();
  });

  it("keeps a conflicting draft visible until staff refreshes", async () => {
    server.use(
      http.patch("*/api/v1/clinics/:id", () =>
        HttpResponse.json(
          { error: { code: "version_conflict", message: "Changed", details: [] } },
          { status: 409 },
        ),
      ),
    );
    renderApp("/?q=Seaside");
    const all = await screen.findByRole("region", { name: "All leads" });
    await userEvent.click(await within(all).findByRole("button", { name: "Edit row" }));
    await userEvent.type(screen.getByLabelText("Contact person"), "Unsaved Person");
    await userEvent.click(screen.getByRole("button", { name: "Save row" }));
    expect(await screen.findByText(/Someone changed this row/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("Unsaved Person")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save row" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Refresh row" }));
    await waitFor(() => expect(screen.queryByDisplayValue("Unsaved Person")).toBeNull());
  });

  it("shows an empty search without hiding the due table", async () => {
    renderApp("/?q=no-such-clinic");
    expect(await screen.findByText(/No search results/)).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Due today" })).toBeInTheDocument();
  });
});
