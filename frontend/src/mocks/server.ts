import { setupServer } from "msw/node";

import { handlers } from "./handlers";

// Used by Vitest so tests hit the same mock API as the browser.
export const server = setupServer(...handlers);
