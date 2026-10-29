import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/client";
import { MOCK_USER } from "@/mocks/data";

import { createQueryClient, SESSION_QUERY_KEY } from "./query-client";

const sessionEnded = new ApiError(401, {
  error: { code: "unauthorized", message: "Sign in required", details: [] },
});

describe("query client", () => {
  it("drops cached leads when any request finds the session has ended", async () => {
    const client = createQueryClient();
    client.setQueryData(SESSION_QUERY_KEY, MOCK_USER);
    client.setQueryData(["leads", "due"], { items: ["private lead row"] });

    await client
      .fetchQuery({ queryKey: ["leads", "all"], queryFn: () => Promise.reject(sessionEnded) })
      .catch(() => {});

    expect(client.getQueryData(SESSION_QUERY_KEY)).toBeNull();
    expect(client.getQueryData(["leads", "due"])).toBeUndefined();
  });
});
