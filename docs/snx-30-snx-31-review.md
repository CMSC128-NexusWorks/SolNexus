# PR #22 review resolution

Rebuilt on main after merged PR #21. The replacement history separates contract, backend and frontend work; it does not retain the original single feature commit.

| Review finding | Resolution |
|---|---|
| Migration clash | Main's pipeline migration 0020 is retained. The obsolete publication migration is removed; only replay migration 0022 is added, directly following 0020. A dummy 0021 is unnecessary. A fresh upgrade has one head, 0022. |
| Two publication ledgers / premature freshness | Removed `app.silver_publication` and the dbt run-end hook. API reads `app.pipeline_status.last_succeeded_data_as_of` for `silver_publish`, which changes only on a successful atomic Airflow swap. Running/failed builds preserve the previous snapshot time. |
| Deleted auth examples | Restored `auth.session_response` and `auth.invalid_credentials` verbatim from main. |
| Inquiry-name error and presentation fields | API and mock return 422 `confirmation_evidence_required` for inquiry-name patches. Fixture rows contain API fields only; display labels are rendered by the UI. |
| Ad-hoc query/mutation keys | All lead hooks, pagination, mutations and invalidation use `features/leads/queries.ts` and `leadKeys`; pipeline health has a shared key/hook. |
| Raw form/table elements | Feature screens now use the existing shadcn Input, Select and Table system plus an accessible Radix/shadcn-style Checkbox wrapper. |
| Inquiry mock accepted forbidden fields | Mock and backend reject inquiry geography/person-spoken-to/derived/unknown fields and validate drafts before applying any changes. |
| Missing docstrings | Added purpose/security docstrings to edits, confirmation, cursor helpers, metadata and detail reads. |
| Every database error reported as retryable | Connection/operational outages yield 503; known uniqueness/reference conflicts yield 409; programming/check defects yield a sanitized 500. No SQL parameters/diagnostics are returned or logged by that handler. |
| Atomic commits | Contract, backend and frontend are separate ticket-scoped commits based on current main. |
| SNX-60 states and warning bar | Mock scenario selector triggers every requested state. Dashboard warnings cover failed/retrying, stale and never-published pipelines while retaining the last good data. |
| SNX-61 validation tests | Tests retain rejected drafts, associate the error with the email field, and verify no partial mock update. Save/cancel/conflict coverage remains. |
| Pipeline endpoint unused/unmocked | Added typed mock and API client; SyncStatus and PipelineWarning use the shared pipeline-status hook. |
| Topic actually showed next step | Backend exposes nullable latest linked interaction topic; Suggested topic and Next step are separate columns. |
| Optional business date missing | `/leads/due?date=YYYY-MM-DD` is implemented, validated and cursor-scoped; omission uses Manila today. |
| Date-filter scope | Removed the dashboard's next-action-date filter, preserving SNX-58's search/status scope. Backend-only SNX-30 filtering remains documented; no product expansion or message to JM was needed. |

## Verification

* Backend: 55 PostgreSQL-backed/auth/error regression tests passed, including a fresh main-to-0022 migration chain.
* Frontend: 40 tests passed; TypeScript, ESLint and Vite production build passed.
* Existing SNX-33 run-status and atomic-silver-publication suites: 32 tests passed against a separate disposable PostgreSQL database.
* Real browser/API: login, due exclusions, validation/save, filtered return, shadcn question/reply confirmation, pipeline reads and desktop/mobile rendering passed using only synthetic fixtures.
* Mock browser: the visible selector demonstrated loading, empty due, no results, API failure, expired session/recovery, failed/stale pipeline and validation.

Docker Desktop's Linux daemon was unavailable in the authoring session, so database tests used the project's pytest suites directly against isolated local PostgreSQL 18.4. Docker remains the documented team test path; its API service now mounts dbt model and contract-fixture sources read-only for those tests.

## Integration boundaries

The actual SNX-28 XLSX upload acceptance check, deployment/privacy review, product approval of existing proposed defaults and operator scheduling of remaining replay jobs are still separate team integration work. The browser fixture does not claim a workbook import. Databases already stamped with an old conflicting revision history require an explicit reconciliation plan or a separate disposable development database; do not assume an in-place `upgrade head` repairs that history.
