# SNX-30 / SNX-31 review handoff

This branch is based on main after PR #21 (SNX-33). It provides authenticated lead queries, versioned audited edits, evidence-gated clinic confirmation, and the dashboard/detail workflows. Team review and end-to-end workbook-import acceptance still apply.

## Migration and publication ownership

Main owns `0020_create_pipeline_runs.py`. This PR retains the requested renumbering of the replay migration to `0022_identity_replay_jobs.py`, with `down_revision = "0020"`. The competing publication migration and dbt run-end hook were removed, rather than assigning them a replacement revision. This PR therefore needs no dummy 0021 migration; `alembic heads` must report the single head `0022`.

`/api/v1/pipeline/status` reads `app.pipeline_status`, created by main's migration 0020. `published_at` is the `silver_publish` row's `last_succeeded_data_as_of`: the build snapshot time recorded by the successful atomic Airflow swap. Building or testing `silver_build`, failing a run, or reading/editing a lead does not advance it. dbt never writes application tables. The endpoint exposes only status/timestamp fields; diagnostics, DAG/run IDs, counts and credentials stay private.

The dashboard fetches that endpoint through `usePipelineStatus`. It warns when a pipeline fails/retries, when no publication exists, or when its age exceeds `PIPELINE_STALE_AFTER_MINUTES` (default 120). This configurable operational warning is not approval of a product freshness SLA.

For development databases that already ran an older version of this PR's conflicting 0020/0021 revisions, use a separate disposable database for validation. Do not assume that `upgrade head` repairs an already-stamped, different migration history; preserving a populated database requires an explicit reconciliation plan.

## Run and test

Use the repository README for Docker environment setup. From the project root:

```sh
docker compose build --build-arg INSTALL_DEV=true api
docker compose up -d postgres
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.staff_account staff@example.test
docker compose run --rm api pytest -q
```

The API's test database is `<DATABASE_URL database>_test`. The dev API service mounts dbt models and contract fixtures read-only so its integration tests can check the source-of-truth examples. Tests do not overwrite development rows.

For the application, publish silver through the SNX-33 `transform_bronze_to_silver` DAG as documented in `airflow/README.md`. A standalone local dbt build does not create a successful pipeline run or mark its tables as published. Start API/web after setup, with `VITE_USE_MOCKS=false` for real API verification. Missing migrations or programming defects return sanitized 500 errors; connection outages return 503; known uniqueness/reference conflicts return 409.

Frontend checks, from `frontend/`:

```sh
npm ci
npm run typecheck
npm run lint
npm run format:check
npm run test
npm run build
```

The UI retains the project's shadcn component system. Queries/mutations, cursor handling, keys and invalidation are centralized in `features/leads/queries.ts`. Due today, Needs clinic name and All leads paginate separately; the status/search URL survives detail navigation. The dashboard date-filter control was removed to keep SNX-58 within scope. API-only `next_action_date` filtering remains part of SNX-30, and `/leads/due?date=YYYY-MM-DD` supports explicit staff/operator tests.

## Demo states and edits

Set `VITE_USE_MOCKS=true`, restart Vite, and sign in using the synthetic credentials shown in development. The **Mock scenario** selector is available even after an expired session redirects to sign-in. It triggers normal, two-second loading, empty due, no search results, API failure, expired session, failed/stale pipeline and field-validation states. Changing it resets cached responses. The control is absent when mocks are disabled.

Row edits send only changed operational fields and the required version. Null is an explicit audited clear. Cancel discards the draft; validation retains it with a field-associated message; a stale version requires refresh. Inquiry mocks and backend both forbid geography and derived fields, and reject name patches with `confirmation_evidence_required`. The fixture contains API fields only, without UI-derived display labels.

The Suggested topic column displays the latest currently linked interaction topic, separately from operational Next step. Unknown topics remain unknown. No message suggestion writes operational fields automatically.

Email to ask opens a mail-client draft, not an automatic send or recorded question. Clinic confirmation requires persisted outbound-question/inbound-reply evidence for the exact complete source identity. It records the clinic/mapping/audits and closes the inquiry atomically. Up to 100 historical messages are replayed immediately; run `python -m app.leads.replay` from backend to drain durable remaining jobs. Conflicting evidence stays in review, and history checks current links even before a new silver publication.

## Acceptance limits

All test data is synthetic. SNX-28's workbook importer remains required for an actual XLSX-upload-to-dashboard acceptance check. Operator scheduling of remaining replay jobs, deployment/privacy checks, and product approval of the proposed contract defaults remain team integration steps. No advanced date-filter UI, call logging, snooze or collapse scope was added.
