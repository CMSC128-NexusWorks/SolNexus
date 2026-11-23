import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

// Synthetic bytes: the mock API never parses the file, and nothing here resembles client data.
const workbook = (name = "synthetic-lead-import-v1.xlsx", bytes = "synthetic workbook") =>
  new File([bytes], name, { type: XLSX });

async function upload(user: ReturnType<typeof userEvent.setup>, file: File) {
  await user.upload(await screen.findByLabelText("Workbook file"), file);
  await user.click(screen.getByRole("button", { name: "Upload workbook" }));
}

/** SNX-62: the upload screen over the real router, query cache, API client and mock API. */
describe("SNX-62 workbook import", () => {
  it("is reachable from the app shell and shows the upload's results", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/");
    await user.click(await screen.findByRole("link", { name: "Import workbook" }));
    await upload(user, workbook());

    expect(await screen.findByRole("heading", { name: "Import results" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/imports/20000000-0000-4000-8000-000000000001");
    expect(
      await screen.findByText(/synthetic-lead-import-v1\.xlsx · uploaded/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Some rows are held until staff decide/)).toBeInTheDocument();

    const summary = screen.getByRole("region", { name: "Summary" });
    const count = (label: string) =>
      within(summary).getByText(label).nextElementSibling?.textContent;
    expect(count("Clinics created")).toBe("2");
    expect(count("Rows accepted")).toBe("2");
    expect(count("Rows held for review")).toBe("2");
    expect(count("Rows rejected")).toBe("2");
    expect(count("Blank rows skipped")).toBe("0");

    // Both Harborview rows are one review group, each pointing at the other sheet's row.
    const held = screen.getByRole("region", { name: "Held for review (2)" });
    const heldRows = within(held).getAllByRole("row").slice(1);
    expect(heldRows).toHaveLength(2);
    expect(heldRows[0]).toHaveTextContent("Harborview Clinic");
    expect(heldRows[0]).toHaveTextContent("Ljs Calling Sheet row 1 (same name, same email)");
    expect(within(heldRows[0]).getAllByRole("cell")[0]).toHaveTextContent("1");
    expect(within(heldRows[1]).getAllByRole("cell")[0]).toHaveTextContent("1");

    const rejected = screen.getByRole("region", { name: "Rejected rows (2)" });
    expect(within(rejected).getAllByText("No clinic name")).toHaveLength(2);

    const warnings = screen.getByRole("region", { name: "Warnings" });
    expect(warnings).toHaveTextContent(/Extra columns kept aside.*: 1 row/);
  });

  it("says so when the same file is uploaded again", async () => {
    const user = userEvent.setup();
    renderApp("/imports");
    await upload(user, workbook());
    await screen.findByRole("heading", { name: "Import results" });
    expect(screen.queryByText("This file was already imported")).toBeNull();

    await user.click(screen.getByRole("link", { name: "Upload another workbook" }));
    await upload(user, workbook());
    expect(await screen.findByText("This file was already imported")).toBeInTheDocument();
    expect(screen.getByText(/No new clinics or duplicates were created/)).toBeInTheDocument();
  });

  it("refuses a non-xlsx file without uploading it", async () => {
    let uploads = 0;
    server.events.on("request:start", ({ request }) => {
      if (request.method === "POST" && new URL(request.url).pathname === "/api/v1/imports")
        uploads += 1;
    });
    // applyAccept: false lets the test pick a file the picker's accept filter would hide.
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/imports");
    await upload(user, new File(["a,b"], "leads.csv", { type: "text/csv" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Nothing was imported");
    expect(alert).toHaveTextContent("Choose the lead workbook as an .xlsx file.");
    expect(uploads).toBe(0);
    server.events.removeAllListeners();
  });

  it("explains a workbook the API refuses, using only the API's safe details", async () => {
    server.use(
      http.post("*/api/v1/imports", () =>
        HttpResponse.json(
          {
            error: {
              code: "unsupported_workbook_format",
              message: "Workbook format not recognized",
              details: [{ message: "Unknown sheet at position 3" }],
            },
          },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    const { router } = renderApp("/imports");
    await upload(user, workbook());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("doesn't match the expected lead sheets");
    expect(alert).toHaveTextContent("Unknown sheet at position 3.");
    expect(router.state.location.pathname).toBe("/imports");
    // Staff can fix the file and try again without reloading.
    expect(screen.getByRole("button", { name: "Upload workbook" })).toBeEnabled();
  });

  it("disables the button while the upload is in flight", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    server.use(
      http.post("*/api/v1/imports", async () => {
        await gate;
        return HttpResponse.json(
          {
            batch_id: "20000000-0000-4000-8000-000000000001",
            state: "needs_review",
            replayed: false,
          },
          { status: 202 },
        );
      }),
    );
    const user = userEvent.setup();
    renderApp("/imports");
    await upload(user, workbook());

    expect(await screen.findByRole("button", { name: /Importing/ })).toBeDisabled();
    expect(screen.getByLabelText("Workbook file")).toBeDisabled();
    release();
    expect(await screen.findByRole("heading", { name: "Import results" })).toBeInTheDocument();
  });

  it("sends signed-out visitors to sign-in", async () => {
    const { router } = renderApp("/imports", { user: null });
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(screen.queryByLabelText("Workbook file")).toBeNull();
  });

  it("reports an unknown batch instead of an empty result", async () => {
    renderApp("/imports/20000000-0000-4000-8000-00000000ffff");
    expect(await screen.findByRole("alert")).toHaveTextContent("Import not found.");
  });
});
