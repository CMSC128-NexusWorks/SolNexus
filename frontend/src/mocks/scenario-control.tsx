import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FieldSelect } from "@/features/leads/field-select";
import { MOCK_SCENARIOS, getMockScenario, setMockScenario, type MockScenario } from "./scenarios";

/** Visible only with VITE_USE_MOCKS=true; it remains reachable on sign-in after an expired session. */
export function MockScenarioControl() {
  const [scenario, setScenario] = useState(getMockScenario);
  const client = useQueryClient();
  return (
    <aside className="m-4 rounded border bg-muted p-3" aria-label="Synthetic demo scenarios">
      <FieldSelect
        label="Mock scenario"
        value={scenario}
        options={Object.entries(MOCK_SCENARIOS).map(([value, label]) => ({ value, label }))}
        onChange={(value) => {
          const next = value as MockScenario;
          setMockScenario(next);
          setScenario(next);
          // Reset pending/cached responses, including auth, so every scenario can be demonstrated again.
          void client.resetQueries();
        }}
      />
      {scenario === "session-expired" && (
        <p role="alert">
          Your session expired. Choose Normal to return to the synthetic signed-in session.
        </p>
      )}
      {scenario === "no-results" && (
        <p className="mt-2 text-sm">
          Enter a clinic/contact search to display the no-results state.
        </p>
      )}
    </aside>
  );
}
