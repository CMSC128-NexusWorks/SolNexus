"""Contract: the master's real Gmail client and sync (services.gmail_client, services.gmail_sync) against the mock.

What runs for real here: google-auth refreshing an access token from a token file, requests over HTTP, Gmail paging
and history, base64url and RFC 822 parsing, error classification and retries, and the bronze writes in Postgres.
Only Google is replaced, by the mock container, and the mock is driven through its /_mock controls.

Dataset facts these tests rely on (datasets/README.md in the mock): 10 messages; messages.list hides the spam one, so a
full sync lists 9; the draft among them is skipped by the master, so 8 are stored.
"""

from __future__ import annotations

import uuid

import pytest
from conftest import MOCK_MAILBOX
from services.checkpoints import load_checkpoint
from services.gmail_client import GmailClient
from services.gmail_sync import SyncSettings, sync_mailbox
from services.google_api import GoogleAuthError, GoogleQuotaExhausted, RetryPolicy

# The master's backfill query (compose.yaml default). The mock measures it from its own clock, which starts at the
# dataset's seed time, so every seeded message is inside the window whenever the tests run.
SETTINGS = SyncSettings(backfill_query="newer_than:30d")
STORED_SEED_MESSAGES = {"msg-001", "msg-002", "msg-003", "msg-004", "msg-007", "msg-008", "msg-009", "msg-010"}


@pytest.fixture
def sleeps() -> list[float]:
    """Backoff waits the client asked for. Recorded instead of slept, so retry tests run in milliseconds."""
    return []


@pytest.fixture
def gmail(token_file, mock_url, mock_token_uri, sleeps) -> GmailClient:
    """The production client, built from a token file exactly as the ingest DAG builds it. Only its two addresses
    differ from production: where tokens are refreshed and where Gmail lives, both the mock's."""
    return GmailClient.from_token_file(
        token_file,
        token_uri=mock_token_uri,
        api_root=f"{mock_url}/gmail/v1/users/me",
        retry_policy=RetryPolicy(max_retries=3),
        sleep=sleeps.append,
    )


def stored_message_ids(db) -> set[str]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT source_message_id FROM bronze.raw_messages"
            " WHERE source_channel = 'gmail' AND source_account_id = %s",
            (MOCK_MAILBOX,),
        )
        rows = {row[0] for row in cur.fetchall()}
    db.commit()
    return rows


def new_inbound_message() -> dict:
    """A message with an ID no earlier run used, so bronze has never seen it (bronze is append-only)."""
    tag = uuid.uuid4().hex[:8]
    return {
        "id": f"msg-contract-{tag}",
        "thread_id": f"thr-contract-{tag}",
        "labels": ["INBOX"],
        "sent_at": "2026-11-20T09:30:00+08:00",
        "sender": f"Clinic {tag} <owner-{tag}@contract-clinic.example.test>",
        "to": ["sales@soltech.example.test"],
        "subject": "Demo request",
        "body": "Good morning, may we book a demo of your YAKAP EMR?",
    }


def test_full_sync_stores_every_ingestible_message_and_saves_the_cursor(gmail, db, job_run_id):
    summary = sync_mailbox(gmail, db, SETTINGS, job_run_id=job_run_id)

    assert summary["mode"] == "full"
    # Fresh database: all 8 inserted. Re-run: all 8 already stored. Either way, every one is accounted for once.
    assert summary["inserted"] + summary["already_stored"] == 8
    assert summary["skipped_by_label"] == 1  # the draft
    assert STORED_SEED_MESSAGES <= stored_message_ids(db)
    assert load_checkpoint(db, "gmail", MOCK_MAILBOX) == gmail.get_profile()["historyId"]


def test_parsed_direction_and_participant_come_through_the_real_wire_format(gmail, db, job_run_id):
    sync_mailbox(gmail, db, SETTINGS, job_run_id=job_run_id)

    with db.cursor() as cur:
        cur.execute(
            """
            SELECT source_message_id, direction, external_participant_id FROM bronze.raw_messages
            WHERE source_account_id = %s AND source_message_id IN ('msg-002', 'msg-008')
            """,
            (MOCK_MAILBOX,),
        )
        rows = {row[0]: row[1:] for row in cur.fetchall()}
    db.commit()

    assert rows["msg-002"] == ("outbound", "ana.reyes@reyesfamilyclinic.example.test")
    # Non-ASCII display name, RFC 2047-encoded by the mock and decoded by the master's parser.
    assert rows["msg-008"] == ("inbound", "jose.pena@penapediatrics.example.test")


def test_incremental_sync_picks_up_only_new_mail(gmail, db, job_run_id, mock_control):
    sync_mailbox(gmail, db, SETTINGS, job_run_id=job_run_id)
    new_message = new_inbound_message()
    mock_control("gmail/messages", new_message)

    summary = sync_mailbox(gmail, db, SETTINGS, job_run_id=job_run_id)

    assert summary["mode"] == "incremental"
    assert summary["inserted"] == 1 and summary["already_stored"] == 0
    assert new_message["id"] in stored_message_ids(db)
    assert load_checkpoint(db, "gmail", MOCK_MAILBOX) == gmail.get_profile()["historyId"]


def test_history_gap_falls_back_to_a_full_resync_without_duplicates(gmail, db, job_run_id, mock_control):
    sync_mailbox(gmail, db, SETTINGS, job_run_id=job_run_id)
    mock_control("gmail/expire-history")

    summary = sync_mailbox(gmail, db, SETTINGS, job_run_id=job_run_id)
    next_run = sync_mailbox(gmail, db, SETTINGS, job_run_id=job_run_id)

    assert summary["mode"] == "full_resync"
    assert summary["inserted"] == 0 and summary["already_stored"] == 8  # recognized, not stored twice
    # The cursor the resync saved is valid, so the following run is incremental again (not another resync).
    assert next_run["mode"] == "incremental"


def test_throttling_is_ridden_out_by_backoff(gmail, db, job_run_id, mock_control, sleeps):
    mock_control("faults", {"target": "gmail", "kind": "rate_limit", "times": 2, "retry_after_seconds": 2})

    summary = sync_mailbox(gmail, db, SETTINGS, job_run_id=job_run_id)

    assert summary["mode"] == "full"
    assert len(sleeps) == 2 and all(wait >= 2 for wait in sleeps)  # Retry-After honoured


def test_used_up_daily_quota_stops_the_run_and_leaves_no_cursor(gmail, db, job_run_id, mock_control):
    mock_control("faults", {"target": "gmail", "kind": "daily_quota", "times": 1})

    with pytest.raises(GoogleQuotaExhausted):
        sync_mailbox(gmail, db, SETTINGS, job_run_id=job_run_id)

    assert load_checkpoint(db, "gmail", MOCK_MAILBOX) is None  # next run starts from the same place


def test_expired_access_token_is_refreshed_transparently_mid_run(gmail, db, job_run_id, mock_control):
    sync_mailbox(gmail, db, SETTINGS, job_run_id=job_run_id)  # the client now holds an access token
    mock_control("oauth/expire-access-tokens")
    mock_control("gmail/messages", new_inbound_message())

    summary = sync_mailbox(gmail, db, SETTINGS, job_run_id=job_run_id)

    assert summary["mode"] == "incremental" and summary["inserted"] == 1


def test_revoked_consent_is_an_auth_error_that_needs_a_person(
    token_file, mock_url, mock_token_uri, db, job_run_id, mock_control
):
    mock_control("oauth/revoke")
    gmail = GmailClient.from_token_file(token_file, token_uri=mock_token_uri, api_root=f"{mock_url}/gmail/v1/users/me")

    with pytest.raises(GoogleAuthError):
        sync_mailbox(gmail, db, SETTINGS, job_run_id=job_run_id)

    assert load_checkpoint(db, "gmail", MOCK_MAILBOX) is None
