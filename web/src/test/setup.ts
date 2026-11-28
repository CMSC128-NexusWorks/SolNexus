import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "@/mocks/server";
import { resetMockImport, resetMockLeads } from "@/mocks/handlers";

// jsdom has no matchMedia; sonner and responsive components call it.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Node's own FormData class. Under jsdom the global FormData is jsdom's, and Node exposes its class only
// through a parsed body.
const NodeFormData = (await new Response(new URLSearchParams()).formData())
  .constructor as typeof FormData;
// Node's File, which Node's FormData requires (jsdom's File is a different class). Imported by a
// variable name because the app's tsconfig has no Node types and should not gain them for one file.
const nodeBuffer = "node:buffer";
const { File: NodeFile } = (await import(/* @vite-ignore */ nodeBuffer)) as { File: typeof File };

/**
 * Test-only: send a jsdom FormData upload (SNX-62) as a Node FormData with the same files and names.
 * Vitest's own jsdom-to-Node bridge drops each file's name (it arrives as "blob") and the request then
 * fails with "Premature close", although real browsers send these bodies fine. Installed after
 * server.listen() so it runs before MSW's fetch interceptor and the mock API sees a normal upload.
 */
function sendJsdomFormsAsNodeForms() {
  const fetchViaMsw = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    const body: unknown = init?.body;
    if (body instanceof FormData && body.constructor !== NodeFormData) {
      const form = new NodeFormData();
      for (const [key, value] of body.entries()) {
        if (typeof value === "string") form.append(key, value);
        else
          form.append(
            key,
            new NodeFile([await value.arrayBuffer()], value.name, { type: value.type }),
          );
      }
      init = { ...init, body: form };
    }
    return fetchViaMsw(input, init);
  };
}

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  sendJsdomFormsAsNodeForms();
});
afterEach(() => {
  server.resetHandlers();
  cleanup();
  sessionStorage.clear();
  resetMockLeads();
  // The mock import batch changes with decisions and resolutions; each test starts from the upload.
  resetMockImport();
});
afterAll(() => server.close());
