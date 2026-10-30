export const MOCK_SCENARIOS = {
  normal: "Normal",
  loading: "Loading",
  "empty-due": "No leads due today",
  "no-results": "No search results",
  "api-error": "API failure",
  "session-expired": "Expired session",
  "pipeline-failed": "Failed pipeline",
  "pipeline-stale": "Stale pipeline",
  "validation-error": "Row validation error",
} as const;
export type MockScenario = keyof typeof MOCK_SCENARIOS;
const key = "solnexus.mock-scenario";

/** Scenario selection is per-tab synthetic state and never sent to the real backend. */
export function getMockScenario(): MockScenario {
  const value = sessionStorage.getItem(key);
  return value && Object.prototype.hasOwnProperty.call(MOCK_SCENARIOS, value)
    ? (value as MockScenario)
    : "normal";
}
export function setMockScenario(value: MockScenario) {
  sessionStorage.setItem(key, value);
}
