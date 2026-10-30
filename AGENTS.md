# SolNexus

Lead and client communication pipeline for SolTech EMR, our client. Conversations (Gmail in Phase 1; Facebook Page and Viber in Phase 2, only after Phase 1 acceptance) land in PostgreSQL bronze tables, dbt builds silver models, FastAPI serves them, and a React dashboard shows them to SolTech staff. This is a CMSC 128/129 student team project.

## Where to look

- **API shapes, data ownership, import rules:** `docs/contracts/phase1-data-api-v1.md`. Message-to-clinic linking is in `docs/contracts/phase1-identity-v1.md`. The contract is the single source of truth: when it changes, update `frontend/src/lib/api/types.ts` and `frontend/src/mocks/` in the same PR.
- **Scope and sprint targets:** `docs/implementation_roadmap.md`. Phase 1 is the semester deliverable; Phase 2 work starts only after Phase 1 is accepted.
- **Requirement IDs (FR-xx, NFR-xx):** `docs/software_requirements.md`.
- **Screens:** `docs/wireframes/`. They are low-fidelity: follow their structure and fields, not their visual styling.
- **Frontend work:** `frontend/README.md`.
- **Local setup and ports:** `README.md`.

## Data rules

- Fixtures, mocks, tests, logs, Jira and PR text use synthetic data only: invented clinic names, `example.test` emails, placeholder numbers. Real client rows stay in the git-ignored `leads-data/` folder.
- Secrets live in `.env` (git-ignored). File-shaped OAuth credentials and tokens live in the git-ignored `.secrets/` directory. `.env.example` holds placeholders only.

## Code comments

- For every code change made by an AI agent, add meaningful comments or docstrings that explain the purpose and non-obvious decisions, especially data handling, security boundaries, and external API behavior. Keep comments accurate as code changes; avoid comments that merely restate a line of code.

## Terms

- **SolTech staff / "the two SolTech team members"** in the docs are the client's two dashboard users, not our dev team.
- **Lead:** a confirmed clinic or an open inquiry (`record_type`). **Inquiry:** a first contact whose clinic name is still unknown; it shows "Clinic name unknown" until staff confirm the name.

## Team and workflow

- Five developers: JM Briz, Luis Borbolla, Seth Caballero, JP Salomeo, Dan Guevara. Nobody has a fixed dev area. JP Salomeo is Scrum Master; JM Briz is Product Owner and sets backlog priority.
- Work is tracked in Jira project **SNX**. Every branch, commit and PR names its ticket.
- Branch names: `<type>/snx-<number>-short-name`, where type is `feat`, `fix`, `docs` or `chore`.
- Commits follow Conventional Commits with the ticket as scope, e.g. `feat(snx-54): add app shell`.
- PRs go into `main`, which is protected: one approval from someone other than the last pusher, no direct pushes.
- Before opening a PR, run the checks for the area you changed; CI (`.github/workflows/ci.yml`) runs the same commands on every PR into `main`. Frontend: `npm run typecheck && npm run lint && npm run format:check && npm run test` in `frontend/`. Backend: `docker compose run --rm api pytest`. Airflow: `docker compose --profile test run --rm airflow-tests`. dbt has no automated checks yet.
- CI jobs **Frontend**, **Backend** and **Airflow** are required status checks on `main`: a red check blocks the merge. CI uses no secrets, so tests must use synthetic data and mocks only. The Airflow Postgres-backed tests skip in CI (they need `SOLNEXUS_TEST_DATABASE_URL`).
