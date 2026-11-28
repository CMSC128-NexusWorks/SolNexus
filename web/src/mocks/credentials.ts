import type { LoginRequest } from "@/lib/api/types";

// Synthetic account accepted by the mock API only. Matches the contract fixture.
export const MOCK_CREDENTIALS: LoginRequest = {
  email: "staff@example.test",
  password: "example-only",
};
