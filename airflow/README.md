# Airflow: Gmail ingestion and silver publication

Two DAGs run the Phase 1 pipeline (SNX-33):

| DAG | Schedule (Asia/Manila) | Does |
|---|---|---|
| `ingest_email` | Hourly at :00 (`GMAIL_SYNC_SCHEDULE`) | Copies the connected Gmail mailbox into `bronze.raw_messages` (SNX-32). It opens an unknown-name inquiry for each inbound first contact, and it never links a message to a clinic without a staff-confirmed source identity |
| `transform_bronze_to_silver` | After every successful `ingest_email` run, plus hourly at :30 (`SILVER_REFRESH_SCHEDULE`) | `build_silver` runs `dbt build` into `silver_build`. `publish_silver` swaps it in as `silver` and records the publication |

Each DAG allows one active run at a time. The hourly silver run keeps spreadsheet imports and staff edits flowing into silver while Gmail is down. Both schedules are the contract's proposed defaults and still need team approval. The connector code is in [include/solnexus_ingest](include/solnexus_ingest). The DAGs only wire it to Airflow.

| Module | Job |
|---|---|
| `gmail/client.py` | Read-only Gmail REST calls with bounded backoff and error classification |
| `gmail/parsing.py` | Gmail `format=raw` message → `MessageEnvelope` (direction, participant, times) |
| `gmail/sync.py` | Full or incremental listing, page by page, with the checkpoint saved after the last page |
| `store.py` | Bronze insert with replay protection, initial resolution, inquiry, checkpoint, all in one transaction per page |
| `resolution.py` | Identity-contract rules for `linked` / `needs_review` and when to open an inquiry |
| `runs.py` | Run status in `app.pipeline_runs`: `running` at task start, `retrying` / `failed` from task callbacks, `succeeded` with the work |
| `silver.py` | `dbt build` into `silver_build`, then the atomic schema swap and publication record |
| `orchestration.py` | Names the DAGs share: warehouse connection, the `GMAIL_BRONZE` dataset, the schedule timezone |

## How a run works

1. Read the mailbox profile: its address (used as `source_account_id`) and its current `historyId`.
2. **No checkpoint:** list messages matching `GMAIL_BACKFILL_QUERY`. **Checkpoint:** list only messages added since that `historyId`.
3. For each page, skip IDs that bronze already holds, fetch the rest (`format=raw`), skip drafts, spam, trash and chats, and store the page in one transaction.
4. The last page's transaction also saves the new checkpoint. If a run fails midway, the next run starts from the old checkpoint. Pages that were already stored are recognised and skipped.

`raw_payload_bytes` holds the message's RFC 822 bytes, which Gmail never changes. If a stored message comes back with different bytes, the first copy is kept and the new copy goes to `bronze.raw_message_discrepancies`.

## Run it

**One-time setup (Linux):** set `AIRFLOW_UID` in `.env` to your user ID (`id -u`). The OAuth files in `.secrets/` are owner-only, and Airflow must run as that owner to read them. They're mounted read-only at `/opt/airflow/secrets`. If Airflow has already run under the old UID, remove its log volume once (`docker compose down` then `docker volume rm solnexus_airflow_logs`) so the new user can write logs.

1. Authorize the test mailbox once with the SNX-21 probe ([backend/spikes/README.md](../backend/spikes/README.md)). That creates `.secrets/gmail-token.json`.
2. Apply migrations: `docker compose run --rm --no-deps api alembic upgrade head`.
3. Start Airflow (`docker compose up -d`). New DAGs start **paused** (`DAGS_ARE_PAUSED_AT_CREATION`), so nothing runs until you choose to start it. Unpause both DAGs in the UI at `localhost:8080`, or:

   ```bash
   docker compose exec airflow-scheduler airflow dags unpause ingest_email
   docker compose exec airflow-scheduler airflow dags unpause transform_bronze_to_silver
   ```

   To run each DAG once without the scheduler:

   ```bash
   docker compose run --rm airflow-scheduler airflow dags test ingest_email
   docker compose run --rm airflow-scheduler airflow dags test transform_bronze_to_silver
   ```

The task's return value (shown in XCom and the log) contains counts only: `mode`, `pages`, `inserted`, `already_stored`, `duplicate`, `discrepancy`, `quarantined`, `inquiries_opened`, `skipped_by_label`, `deleted_before_fetch`.

| Setting (`.env`) | Default | Meaning |
|---|---|---|
| `GMAIL_LABEL_ID` | empty | Gmail label ID that marks lead mail; applies to every run. Empty means the whole mailbox |
| `GMAIL_BACKFILL_QUERY` | `newer_than:30d` | Gmail search that limits the first sync and any recovery resync |

**Choosing what to ingest is still an open decision.** With `GMAIL_LABEL_ID` empty, every sender becomes a "Clinic name unknown" inquiry, including newsletters and notifications. Until the team agrees on a selection rule, for example a Gmail filter that applies a "SolNexus" label, run against a mailbox that holds only synthetic lead conversations.

## Run status and freshness

Every run writes one row to `app.pipeline_runs`. The dashboard-facing summary is the `app.pipeline_status` view:

```sql
SELECT pipeline, last_run_status, last_run_error_summary, last_succeeded_at, last_succeeded_data_as_of
FROM app.pipeline_status;
```

`last_succeeded_data_as_of` for `silver_publish` is the `published_at` the API shows: the moment the build started reading `bronze` and `app`. `last_succeeded_at` is when it was swapped in. Both change only when a complete, fully tested build has been swapped in, so a failed run never makes data look fresh. `counts` holds the Gmail summary above, or dbt node counts and published row counts for silver. `error_summary` holds an exception class and its first line only. Full tracebacks stay in the Airflow task log.

If a worker is killed mid-task, so that no callback runs, the row can stay `running` or `retrying`. The next run writes its own row, and the view always reports the latest run.

## Failures and recovery

| Symptom | Cause | What to do |
|---|---|---|
| Task fails at once with `Gmail needs operator action: OAuth refresh failed` | Consent expired (External/Testing consent lasts 7 days) or was revoked. A temporary outage of Google's token server is retried instead, like a 5xx | Re-authorize with the SNX-21 probe: remove only `.secrets/gmail-token.json`, rerun the probe, then rerun the DAG. Nothing is lost, because the checkpoint was not advanced |
| Task fails at once with `Gmail refused the request (403 domainPolicy …)` | A Workspace admin policy blocks the app | An admin must allow the app. Retrying won't help |
| Log shows `Gmail call failed (403 rateLimitExceeded); retry …` | Per-user quota throttling | Nothing to do. The client backs off and retries up to 5 times (1 s growing to a 32 s cap, plus jitter) |
| Task fails with `Gmail quota used up (403 dailyLimitExceeded)` | The project's daily quota is used up | Nothing to fix. Airflow retries the task, and the next run continues from the checkpoint once the quota resets. If it keeps happening, check the project's quota in Cloud Console |
| Task fails with `gave up after 5 retries` | Throttling or an outage that lasted longer than the backoff | Airflow retries the task twice, 5 minutes apart. After that, rerun later. Pages already committed are kept |
| Log shows `Stored Gmail historyId expired; running a full resync` and the summary has `mode: full_resync` | The checkpoint is older than Gmail's history retention (about a week) | Nothing to do. The run lists `GMAIL_BACKFILL_QUERY` again, and only messages bronze doesn't have yet are downloaded. Widen the query if the DAG was paused longer than its window |
| `quarantined` > 0 in the summary | A message couldn't be parsed, or Postgres rejected it. The run skipped it so the checkpoint could move on | Check `reason` in `bronze.quarantined_messages`. After fixing the parser, delete the account's row in `app.ingestion_checkpoints` to force a full resync. The message is then stored normally, and the quarantine row stays as history. Many quarantined messages at once usually means a parser bug, not bad mail |
| `discrepancy` > 0 in the summary | A message came back with different bytes | Compare the row in `bronze.raw_message_discrepancies` with its `raw_messages` row. The first copy stays the evidence |
| `build_silver` fails at once with `dbt build failed on N node(s): test.…` | A dbt data test failed, so the new silver would break a contract | Not retried, because rebuilding the same data cannot help. The previous silver and `published_at` stay live. To inspect it, build into a schema of your own: `docker compose run --rm airflow-scheduler bash -c "cd /opt/airflow/dbt && dbt build --vars '{silver_schema: silver_inspect}'"`. **Never** pass `silver_build`: it belongs to the DAG, and publish refuses a build it did not stamp. Fix the data or model, then clear the task in the UI, and drop `silver_inspect` when you are done. The failed build's `silver_build` is dropped at once, so it can never be published |
| `build_silver` fails with `dbt build exited with code …` or a model `error` | Database unreachable, or a SQL or compile error | Retried twice (2 then 4 minutes). If retries run out, check the task log for the dbt output |
| `publish_silver` fails with `LockNotAvailable` | A long API read held silver for more than 30 s during the swap, or a build held the build lock that long | Retried automatically. Nothing changed, because the swap rolled back |
| `build_silver` fails with `BuildInProgressError` | Another build or publish holds the build lock, e.g. an `airflow dags test` beside the scheduler | Retried automatically once the other one finishes |
| `publish_silver` fails at once with `StaleBuildError` | `silver_build` is not this run's passing build: another run rebuilt it, or someone ran dbt into it | Not retried. Clear `build_silver` for this run (that reruns both tasks), or just wait for the next run |
| `app.pipeline_status` shows `silver_publish` succeeded long ago | `transform_bronze_to_silver` is paused, or every run fails | Unpause it, or read `last_run_error_summary` and the task log |

Log lines and errors include status codes, Google's reason, dbt node IDs and counts. They never include tokens, addresses or message content.

**Rerunning safely.** You can clear and rerun any task. `sync_gmail` resumes from the committed checkpoint, and bronze ignores replays. `build_silver` starts from an empty `silver_build`. `publish_silver` swaps in only the build its own run stamped, or changes nothing. Clearing either task on a run that already published does nothing: the run stays `succeeded`, and its publication stays the one recorded. To rebuild silver from scratch, trigger `transform_bronze_to_silver`. Bronze and `app` are never modified by it.

## Tests

The tests run in the Airflow image. The Postgres-backed tests need their **own throwaway** database, `solnexus_ingest_test`, migrated to head. Don't point them at the dev database or at the backend suite's `solnexus_test`: these tests leave rows that can never be deleted (bronze and staff-confirmed mappings are append-only), and that would break the backend suite's cleanup. The fixture refuses any database whose name doesn't end in `_ingest_test`.

```bash
set -a; . ./.env; set +a
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE solnexus_ingest_test"
docker compose run --rm --no-deps -e DATABASE_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres:5432/solnexus_ingest_test" \
  api alembic upgrade head
SOLNEXUS_TEST_DATABASE_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres:5432/solnexus_ingest_test" \
  docker compose --profile test run --rm airflow-tests
```

If `SOLNEXUS_TEST_DATABASE_URL` is not set, only the database tests are skipped. Arguments after the service name go to pytest, for example `docker compose --profile test run --rm airflow-tests -k sync`. All test data is synthetic (`example.test` addresses). Gmail is faked in memory, so the tests never call Google.
