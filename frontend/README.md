# SolNexus frontend

React 19 + TypeScript, built with Vite. UI components come from [shadcn/ui](https://ui.shadcn.com) (Radix base, Tailwind CSS v4).

## Run it

With Docker (from the repo root): `docker compose up web`, then open http://localhost:5173.

Without Docker (from `frontend/`):

```bash
npm install
VITE_USE_MOCKS=true npm run dev
```

`VITE_USE_MOCKS=true` serves the API from `src/mocks/` so you can build screens before the backend endpoints exist. On the login placeholder, click **Continue with mock account**.

> After pulling changes to `package.json`, Docker keeps old packages in the `web_node_modules` volume. Run `docker compose run --rm web npm install` to refresh it.

## Scripts

| Command                       | What it does                                 |
| ----------------------------- | -------------------------------------------- |
| `npm run dev`                 | Dev server with hot reload                   |
| `npm run build`               | Type-check, then production build to `dist/` |
| `npm run typecheck`           | TypeScript only                              |
| `npm run lint`                | ESLint                                       |
| `npm run format`              | Prettier (also sorts Tailwind classes)       |
| `npm run test` / `test:watch` | Vitest + React Testing Library               |

Run `typecheck`, `lint` and `test` before opening a PR.

## Where things go

```
src/
  app/              router, providers, app-level pages
  components/
    ui/             shadcn components (generated; add with the CLI, don't hand-edit unless needed)
    layout/         app shell and top bar
  features/
    auth/           auth context, route guard, login page
    leads/          dashboard, lead detail, data hooks (queries.ts)
  lib/
    api/            typed API client: types.ts mirrors docs/contracts/phase1-data-api-v1.md
    format.ts       date helpers (Asia/Manila business dates)
  mocks/            mock API (MSW) with synthetic data only
  test/             test setup and renderApp() helper
```

## Conventions

- **Fetch data through hooks in `features/*/queries.ts`**, never `fetch` directly in a component. Hooks give you `isPending`, `isError` and `data`.
- **API shapes live in `src/lib/api/types.ts`.** If the contract changes, update the types and `src/mocks/` together.
- **Use shadcn components before writing custom markup.** Add one with `npx shadcn@latest add <name>`. Already installed: button, badge, card, input, label, field, table, skeleton, empty, alert, separator, avatar, spinner, toggle-group, dialog, select, sonner, dropdown-menu.
- **Use semantic colours** (`bg-muted`, `text-muted-foreground`), not raw ones like `bg-gray-500`. Use `flex` + `gap-*` for spacing, not `space-y-*`.
- **Mock data must be synthetic.** Never copy real client rows into `src/mocks/` or tests.
- **Screen placeholders** (`<TicketPlaceholder ticket="SNX-57" …>`) mark what each Jira ticket builds. Replace the placeholder when you take the ticket.
- Branch as `feat/snx-<number>-short-name` and open a PR into `main` (1 approval required).

## Screens and tickets

| Route              | Screen                         | Wireframe | Ticket         |
| ------------------ | ------------------------------ | --------- | -------------- |
| `/login`           | Sign-in                        | 01        | SNX-56         |
| `/`                | Due today + All leads          | 02, 03    | SNX-57, SNX-58 |
| `/leads/:clinicId` | Lead detail + history          | 04        | SNX-59         |
| all                | Loading / empty / error states | 08        | SNX-60         |

Wireframes are in `docs/wireframes/` and in the Figma file "SolTech Leads — Phase 1 Wireframes".
