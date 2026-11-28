import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { exportFilename } from "@/lib/download";
import { businessDate } from "@/mocks/data";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

// jsdom has no object URLs and can't follow a download link, so record what would have been saved.
let saved: { href: string; download: string }[];
beforeEach(() => {
  saved = [];
  URL.createObjectURL = vi.fn(() => "blob:synthetic-export");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push({ href: this.href, download: this.download });
  });
});
afterEach(() => vi.restoreAllMocks());

async function downloadButton() {
  const all = await screen.findByRole("region", { name: "All leads" });
  return within(all).findByRole("button", { name: "Download leads" });
}

describe("SNX-63 download current leads", () => {
  it("saves the export as a dated spreadsheet and shows progress meanwhile", async () => {
    server.use(
      http.get("*/api/v1/leads/export", async () => {
        await delay(50);
        return new HttpResponse(new Uint8Array([0x50, 0x4b]), {
          headers: { "Content-Type": XLSX },
        });
      }),
    );
    renderApp();
    await userEvent.click(await downloadButton());

    expect(await screen.findByRole("button", { name: /Preparing download/ })).toBeDisabled();
    await waitFor(() =>
      expect(saved).toEqual([
        { href: "blob:synthetic-export", download: `solnexus-leads-${businessDate()}.xlsx` },
      ]),
    );
    expect(await downloadButton()).toBeEnabled();
  });

  it("explains that the export ignores search and filters", async () => {
    renderApp("/?status=awaiting_demo");
    expect(await downloadButton()).toHaveAccessibleDescription(/every current lead/i);
  });

  it("shows a retryable message instead of a broken file when the export fails", async () => {
    server.use(
      http.get("*/api/v1/leads/export", () =>
        HttpResponse.json(
          { error: { code: "data_unavailable", message: "Unavailable", details: [] } },
          { status: 503 },
        ),
      ),
    );
    renderApp();
    await userEvent.click(await downloadButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(/Couldn't download the leads/);
    expect(saved).toEqual([]);
    expect(await downloadButton()).toBeEnabled();
  });

  it("sends staff to sign in with a clear message when the session expired", async () => {
    server.use(
      http.get("*/api/v1/leads/export", () =>
        HttpResponse.json(
          { error: { code: "unauthorized", message: "Sign in required", details: [] } },
          { status: 401 },
        ),
      ),
    );
    const { router } = renderApp();
    await userEvent.click(await downloadButton());

    expect(await screen.findByText(/Your session expired/)).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(saved).toEqual([]);
  });

  it("downloads the mock API's CSV export in mock mode", async () => {
    renderApp();
    await userEvent.click(await downloadButton());
    await waitFor(() =>
      expect(saved.map((file) => file.download)).toEqual([`solnexus-leads-${businessDate()}.csv`]),
    );
  });
});

describe("exportFilename", () => {
  // 2026-11-14 20:30 UTC is already 15 Nov in Manila.
  const lateUtc = new Date("2026-11-14T20:30:00Z");

  it("dates the file by the Manila business calendar", () => {
    expect(exportFilename(XLSX, lateUtc)).toBe("solnexus-leads-2026-11-15.xlsx");
  });

  it("follows the response type, ignoring parameters, and defaults to xlsx", () => {
    expect(exportFilename("text/csv; charset=utf-8", lateUtc)).toBe(
      "solnexus-leads-2026-11-15.csv",
    );
    expect(exportFilename("", lateUtc)).toBe("solnexus-leads-2026-11-15.xlsx");
  });
});
