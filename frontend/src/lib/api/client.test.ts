import { describe, expect, it } from "vitest";

import { login } from "./auth";
import { ApiError } from "./client";
import { getLeads } from "./leads";

describe("apiFetch", () => {
  it("passes query parameters through to the API", async () => {
    const page = await getLeads({ status: "awaiting_demo" });

    expect(page.items.map((lead) => lead.clinic_name)).toEqual(["Lakeside Diagnostics"]);
  });

  it("throws ApiError with the contract error code", async () => {
    const failure = login({ email: "staff@example.test", password: "wrong" });

    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({ status: 401, code: "invalid_credentials" });
  });
});
