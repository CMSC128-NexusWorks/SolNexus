# Database schema and ownership

The Phase 1 business schema lives in the `solnexus` PostgreSQL database. Airflow keeps its own metadata in the separate `airflow` database, which migrations never touch. Design rationale is in [the ERD draft](contracts/phase1-erd-schema-draft.md) and [the identity contract](contracts/phase1-identity-v1.md); this page records what is implemented.

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
- Parsed status or next-action values are suggestions with a `parser_version`; they never change `app` rows.

`silver.leads`: one row per confirmed clinic or open inquiry, unique on `(record_type, lead_id)`.

- `record_type = 'clinic'` comes from `app.clinics`; `record_type = 'inquiry'` comes from `app.lead_inquiries` where `state = 'open'`, with `clinic_name` null and `clinic_name_state = 'unknown'`.
- Operational fields come from `app` unchanged. `last_interaction_at` and `interaction_count` are derived from linked `silver.interactions`.
- Clinics with no messages still appear.

dbt tests on these models should check uniqueness of the keys above and relationships to their `app` and `bronze` sources.
