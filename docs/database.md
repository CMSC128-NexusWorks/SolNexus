# Database schema and ownership

The Phase 1 business schema lives in the `solnexus` PostgreSQL database. Airflow keeps its own metadata in the separate `airflow` database, which migrations never touch. Design rationale is in [the ERD draft](contracts/phase1-erd-schema-draft.md) and [the identity contract](contracts/phase1-identity-v1.md); this page records what is implemented.

## Running migrations

Migrations live in [backend/migrations/versions](../backend/migrations/versions) and run through the `api` image. Run them explicitly; the API does not migrate on startup.

**Fresh setup or after pulling new migrations:**

```bash
docker compose up -d postgres
docker compose build api                                   # only when backend/requirements.txt changed
docker compose run --rm --no-deps api alembic upgrade head
docker compose run --rm --no-deps api alembic current      # expect the newest revision with (head)
```

**Existing volume:** the same commands. Alembic records applied revisions in `public.alembic_version` and runs only the missing ones, so an existing scaffold database upgrades in place. Do not use `docker compose down -v` to "reset" a database: it deletes the volume.

Postgres runs `docker/postgres/init.sql` only when its volume is empty, which is why business tables are not created there.

**Synthetic development data** (optional, safe to rerun):

```bash
set -a; . ./.env; set +a
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
  < backend/fixtures/dev_seed.sql
```

**Review the SQL of a migration without a database:** `docker compose run --rm --no-deps api alembic upgrade head --sql`.

**Adding a migration:** create the next numbered file in `backend/migrations/versions` with `docker compose run --rm --no-deps api alembic revision --rev-id 0015 -m "create app.example"` (pass the next number; without `--rev-id` Alembic uses a random hash). Write the DDL by hand with `op.execute`, include a `downgrade`, and before opening a PR check `upgrade head`, `downgrade -1`, `upgrade head` and the `--sql` output against a throwaway database. A downgrade drops its tables with their rows, so never run one against a database whose data you need.

## Who owns what

Each schema has exactly one tool that changes its structure.

| Schema | Structure owned by | Rows written by | Rebuilt? |
|---|---|---|---|
| `bronze` | Alembic (`backend/migrations`) | Ingestion connectors, insert only | Never |
| `app` | Alembic (`backend/migrations`) | API, ingestion, import, resolution job | Never |
| `silver` | dbt (`dbt/models/silver`) | dbt only | Yes, on any dbt run |
| `public` | Alembic's `alembic_version` table and the `citext` extension | Alembic | No |

Rules that follow from this:

- dbt reads `bronze` and `app` through [dbt/models/sources.yml](../dbt/models/sources.yml) and never writes to them. A staff edit stored in `silver` would be lost on the next dbt run.
- The API never writes to `silver`. It reads silver, plus `app` rows for edits not yet projected (`pending_projection`).
- A schema change to `bronze` or `app` is a new Alembic revision. Never edit a merged revision.

## Tables

| Table | Holds | Change rule |
|---|---|---|
| `bronze.raw_messages` | One row per source message: exact payload bytes, source IDs, event and ingest times | Append-only. `INSERT ... ON CONFLICT DO NOTHING` on `raw_messages_source_key` |
| `app.staff_users` | The SolTech dashboard accounts | Deactivate with `is_active`; never delete |
| `app.clinics` | Confirmed clinic leads | Versioned edits: `SET ..., version = version + 1 WHERE version = :expected` |
| `app.lead_inquiries` | Unknown-name first contacts | Versioned edits, as for clinics |
| `app.clinic_source_identities` | Staff-confirmed source identity to clinic links | Revoke once, then insert a replacement; no other change |
| `app.message_resolutions` | Current `linked` or `needs_review` decision per message | Update; write a resolution event in the same transaction |
| `app.message_resolution_events` | History of changed resolutions | Append-only |
| `app.clinic_field_events` | Audit of staff row edits and name confirmations | Append-only |
| `app.clinic_status_events` | Staff status transitions and import baselines | Append-only |
| `app.import_batches`, `app.import_rows` | Workbook uploads and per-row results | Update while processing |
| `app.import_field_reviews`, `app.import_field_review_candidates` | Cross-sheet value conflicts and their staff decisions | Update to resolve |

Append-only tables reject `UPDATE`, `DELETE` and `TRUNCATE` with a trigger. Every service currently connects as one superuser, which bypasses `GRANT`/`REVOKE`, so the triggers are what stops accidental edits. They do not stop an owner who disables them.

## Silver contract (built by SNX-29)

`silver.interactions`: one row per `bronze.raw_messages` row, unique on `raw_message_id`.

- `clinic_id` is set only when the message's `app.message_resolutions` row is `linked` **and** an active `app.clinic_source_identities` row for the message's exact `(source_channel, source_account_id, external_participant_id)` points to the same clinic. Otherwise it is null and the row stays available for review.
- Parsed status or next-action values are suggestions with a `parser_version`; they never change `app` rows. `topic`, `derived_status_code`, `derived_next_action_date` and `parser_version` exist but stay null until the baseline rules are approved and ingestion fills `parsed_payload`.

`silver.leads`: one row per confirmed clinic or open inquiry, unique on `(record_type, lead_id)`.

- `record_type = 'clinic'` comes from `app.clinics`; `record_type = 'inquiry'` comes from `app.lead_inquiries` where `state = 'open'`, with `clinic_name` null and `clinic_name_state = 'unknown'`.
- Operational fields come from `app` unchanged. `last_interaction_at` and `interaction_count` are derived from linked `silver.interactions`.
- Every silver row is a snapshot as of the last successful dbt run (`published_at`). A mapping revocation or correction made after that run still counts toward the old clinic's `last_interaction_at` and `interaction_count` until the next run. Clinic history must apply the read-time link check in [the data/API contract](contracts/phase1-data-api-v1.md); whether the API also recomputes these two columns at read time, or shows them as of `published_at`, is open for SNX-30.
- Clinics with no messages still appear.

dbt tests on these models should check uniqueness of the keys above and relationships to their `app` and `bronze` sources.
