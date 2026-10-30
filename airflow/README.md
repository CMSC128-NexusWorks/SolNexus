# Airflow and the Gmail connector

The `ingest_email` DAG copies the connected Gmail mailbox into `bronze.raw_messages` (SNX-32). It opens an unknown-name inquiry for each inbound first contact, and it never links a message to a clinic without a staff-confirmed source identity. The connector code is in [include/solnexus_ingest](include/solnexus_ingest). The DAG only wires it to Airflow. Scheduling belongs to SNX-33, so for now the DAG runs only when you trigger it.

| Module | Job |
|---|---|
| `gmail/client.py` | Read-only Gmail REST calls with bounded backoff and error classification |
| `gmail/parsing.py` | Gmail `format=raw` message → `MessageEnvelope` (direction, participant, times) |
| `gmail/sync.py` | Full or incremental listing, page by page, with the checkpoint saved after the last page |
| `store.py` | Bronze insert with replay protection, initial resolution, inquiry, checkpoint, all in one transaction per page |
| `resolution.py` | Identity-contract rules for `linked` / `needs_review` and when to open an inquiry |

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
3. Start Airflow (`docker compose up -d`), unpause `ingest_email` in the UI at `localhost:8080`, and trigger it. You can also run it once without the scheduler:

   ```bash
   docker compose run --rm airflow-scheduler airflow dags test ingest_email
   ```

The task's return value (shown in XCom and the log) contains counts only: `mode`, `pages`, `inserted`, `already_stored`, `duplicate`, `discrepancy`, `quarantined`, `inquiries_opened`, `skipped_by_label`, `deleted_before_fetch`.

| Setting (`.env`) | Default | Meaning |
|---|---|---|
| `GMAIL_LABEL_ID` | empty | Gmail label ID that marks lead mail; applies to every run. Empty means the whole mailbox |
| `GMAIL_BACKFILL_QUERY` | `newer_than:30d` | Gmail search that limits the first sync and any recovery resync |

**Choosing what to ingest is still an open decision.** With `GMAIL_LABEL_ID` empty, every sender becomes a "Clinic name unknown" inquiry, including newsletters and notifications. Until the team agrees on a selection rule, for example a Gmail filter that applies a "SolNexus" label, run against a mailbox that holds only synthetic lead conversations.

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

Log lines and errors include status codes, Google's reason and counts. They never include tokens, addresses or message content.

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
