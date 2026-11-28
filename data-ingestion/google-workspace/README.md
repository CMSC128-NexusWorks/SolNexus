# Google Workspace connector (SNX-67)

Reads SolTech's Gmail and Google Calendar, read-only, and writes them to the `bronze` and `app` schemas.
SolTech bookings go from the web booking app to Calendly to Google Calendar, so calendar events next to
email give staff the full picture of every lead.

The layout follows the Glynac Google Workspace connector this design is modeled on: a master that talks to
Google, a mock of Google for local runs and tests, and the contracts between them.

| Folder | What it is | Status |
|---|---|---|
| `google-workspace-master-service/` | Talks to Google: fetch, parse, store to bronze, keep each source's sync cursor. Flat layout: `services/` for logic, `tests/unit/` for tests | Gmail extraction moved here from `airflow/include` |
| `google-workspace-mock-server/` | A fake Gmail and Calendar API seeded with synthetic data, so the master can run end to end with no Google account | Planned (built before the pipeline work) |
| `contracts/` | Machine-readable contracts: the master's scan API and the record shapes it writes | Planned |
| `contract-tests/` | The real master against the mock, end to end | Planned |
| `docs/` | Authorization, field mapping, incremental sync, running the master | Planned |

## How it fits the rest of SolNexus

```
Google (or the mock) ──▶ master service ──▶ Postgres bronze.* / app.*  ──▶ dbt silver ──▶ API ──▶ dashboard
                              ▲
                  Airflow starts and watches scans
```

**Adopted from the Glynac design:** a separate master per provider, a mock server for credential-free tests,
contract tests, page-by-page fetch → parse → store with the cursor saved only after the last page, and one
shared Google API layer (auth, retries, error classes) under every Google product.

**Left out, on purpose:**

- *The core / coordinator service.* SolNexus has one client and no scan coordinator. Airflow plays that role.
- *Kafka and Flink.* At SolTech's volume the master writes bronze directly, in one transaction per page.
- *A separate database for the master.* SolNexus keeps one Postgres. Every table, including the master's,
  is created by the backend's Alembic migrations ([docs/database.md](../../docs/database.md)).
- *PII masking.* SolTech staff are the data owners and read the real conversations. Logs still never carry
  addresses or content.

## Transition

Until the master has its scan API, Airflow's `ingest_email` DAG imports the master's `services` package
directly (mounted read-only and put on `PYTHONPATH` in `compose.yaml`). When the scan API lands, the DAG
switches to calling it over HTTP and that mount is removed.

## Tests

```bash
docker compose --profile test run --rm google-workspace-master-tests
```

The Postgres-backed tests use the same throwaway `solnexus_ingest_test` database as the Airflow tests; see
[airflow/README.md](../../airflow/README.md#tests) for creating it, and set `SOLNEXUS_TEST_DATABASE_URL`.
