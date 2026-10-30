"""Write message envelopes to bronze and their initial resolution to app, one page per transaction.

Replay protection: bronze.raw_messages is unique on (source_channel, source_account_id,
source_message_id) and the insert uses ON CONFLICT DO NOTHING, so a retried page stores nothing
twice. A message is resolved only on its first insert; a replay never touches its resolution.

Atomicity: store_page writes every message of a page, and optionally the connector checkpoint, in a
single transaction. A crash before commit loses the whole page and leaves the old checkpoint, so the
next run fetches the page again instead of skipping it.

Poison messages: a message PostgreSQL rejects (e.g. a value a constraint or jsonb refuses) is rolled
back to a per-message savepoint and quarantined, so one bad message cannot fail every future run.
Connection-level errors are NOT caught: they abort the page and the run retries it later.
"""

from __future__ import annotations

import enum
import hashlib
import logging
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import psycopg2
from psycopg2.extensions import connection as Connection
from psycopg2.extensions import cursor as Cursor
from psycopg2.extras import Json

from solnexus_ingest.envelope import MessageEnvelope, QuarantinedMessage
from solnexus_ingest.resolution import Resolution, decide, opens_inquiry

log = logging.getLogger(__name__)


class StoreOutcome(str, enum.Enum):
    INSERTED = "inserted"
    DUPLICATE = "duplicate"  # same key, same bytes: an ordinary replay
    DISCREPANCY = "discrepancy"  # same key, different bytes: kept for review
    QUARANTINED = "quarantined"  # unparseable or rejected by PostgreSQL: kept for review, run continues


@dataclass(frozen=True)
class Checkpoint:
    source_channel: str
    source_account_id: str
    cursor_value: str


def store_page(
    conn: Connection,
    items: Iterable[MessageEnvelope | QuarantinedMessage],
    job_run_id: str,
    checkpoint: Checkpoint | None = None,
) -> Counter[str]:
    """Store one page atomically and return counts per outcome plus 'inquiries_opened'.

    items are envelopes, plus QuarantinedMessage records for messages the connector could not parse.
    job_run_id identifies the run in app.message_resolution_events (the system actor).
    """
    counts: Counter[str] = Counter()
    try:
        with conn.cursor() as cur:
            for item in items:
                if isinstance(item, QuarantinedMessage):
                    outcome, opened_inquiry = quarantine(cur, item, job_run_id), False
                else:
                    outcome, opened_inquiry = _store_or_quarantine(cur, item, job_run_id)
                counts[outcome.value] += 1
                counts["inquiries_opened"] += int(opened_inquiry)
            if checkpoint is not None:
                save_checkpoint(cur, checkpoint)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return counts


def _store_or_quarantine(cur: Cursor, envelope: MessageEnvelope, job_run_id: str) -> tuple[StoreOutcome, bool]:
    """store_envelope inside a savepoint; a data-level rejection quarantines just this message."""
    cur.execute("SAVEPOINT store_message")
    try:
        result = store_envelope(cur, envelope, job_run_id)
    except (psycopg2.DataError, psycopg2.IntegrityError) as exc:
        # DataError: a value PostgreSQL cannot store (bad encoding, out-of-range). IntegrityError: a
        # constraint the parser should have satisfied. Both are about this message, not the database.
        cur.execute("ROLLBACK TO SAVEPOINT store_message")
        reason = f"db_rejected:{type(exc).__name__}"
        return quarantine(cur, QuarantinedMessage.from_envelope(envelope, reason), job_run_id), False
    cur.execute("RELEASE SAVEPOINT store_message")
    return result


def quarantine(cur: Cursor, item: QuarantinedMessage, job_run_id: str) -> StoreOutcome:
    """Record a message the run is skipping. A repeat of the same message keeps the first record."""
    cur.execute(
        """
        INSERT INTO bronze.quarantined_messages (
            source_channel, source_account_id, source_message_id, reason, payload_bytes, job_run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT ON CONSTRAINT quarantined_messages_source_key DO NOTHING
        """,
        (item.source_channel, item.source_account_id, item.source_message_id, item.reason, item.payload_bytes,
         job_run_id),
    )
    log.warning("Quarantined a %s message (%s)", item.source_channel, item.reason)
    return StoreOutcome.QUARANTINED


def store_envelope(cur: Cursor, envelope: MessageEnvelope, job_run_id: str) -> tuple[StoreOutcome, bool]:
    """Insert one message, or classify the replay. Returns (outcome, whether an inquiry was opened)."""
    cur.execute(
        """
        INSERT INTO bronze.raw_messages (
            source_channel, source_account_id, source_message_id, source_thread_id,
            external_participant_id, direction, source_sender_id, source_recipient_ids,
            source_event_at, raw_payload_bytes, parsed_payload
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT ON CONSTRAINT raw_messages_source_key DO NOTHING
        RETURNING raw_message_id
        """,
        (
            envelope.source_channel,
            envelope.source_account_id,
            envelope.source_message_id,
            envelope.source_thread_id,
            envelope.external_participant_id,
            envelope.direction,
            envelope.source_sender_id,
            Json(list(envelope.source_recipient_ids)),
            envelope.source_event_at,
            envelope.raw_payload_bytes,
            Json(_jsonb_safe(envelope.parsed_payload)),
        ),
    )
    row = cur.fetchone()
    if row is None:
        return _classify_replay(cur, envelope, job_run_id), False

    raw_message_id = row[0]
    resolution = decide(envelope, _active_mappings(cur, envelope), _candidate_clinics(cur, envelope))
    _insert_resolution(cur, raw_message_id, resolution, job_run_id)
    opened = opens_inquiry(envelope, resolution) and _open_inquiry(cur, envelope, raw_message_id)
    return StoreOutcome.INSERTED, opened


def save_checkpoint(cur: Cursor, checkpoint: Checkpoint) -> None:
    cur.execute(
        """
        INSERT INTO app.ingestion_checkpoints (source_channel, source_account_id, cursor_value)
        VALUES (%s, %s, %s)
        ON CONFLICT (source_channel, source_account_id) DO UPDATE SET cursor_value = EXCLUDED.cursor_value
        """,
        (checkpoint.source_channel, checkpoint.source_account_id, checkpoint.cursor_value),
    )


def stored_message_ids(conn: Connection, source_channel: str, source_account_id: str, message_ids: list[str]) -> set[str]:
    """Which of these source message IDs bronze already holds for this account.

    Lets a connector skip downloading messages it has stored before (resyncs, retried pages).
    Quarantined messages are deliberately not included, so a later resync retries them.
    """
    if not message_ids:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_message_id FROM bronze.raw_messages
            WHERE source_channel = %s AND source_account_id = %s AND source_message_id = ANY(%s)
            """,
            (source_channel, source_account_id, message_ids),
        )
        found = {row[0] for row in cur.fetchall()}
    conn.commit()  # end the read-only transaction; the page is written in its own transaction
    return found


def load_checkpoint(conn: Connection, source_channel: str, source_account_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cursor_value FROM app.ingestion_checkpoints WHERE source_channel = %s AND source_account_id = %s",
            (source_channel, source_account_id),
        )
        row = cur.fetchone()
    conn.commit()  # end the read-only transaction so the connection does not sit "idle in transaction"
    return row[0] if row else None


def _classify_replay(cur: Cursor, envelope: MessageEnvelope, job_run_id: str) -> StoreOutcome:
    """Compare a replay with the stored first copy; keep a differing copy as a discrepancy."""
    cur.execute(
        """
        SELECT raw_message_id, raw_payload_sha256 FROM bronze.raw_messages
        WHERE source_channel = %s AND source_account_id = %s AND source_message_id = %s
        """,
        (envelope.source_channel, envelope.source_account_id, envelope.source_message_id),
    )
    raw_message_id, stored_sha256 = cur.fetchone()
    if bytes(stored_sha256) == hashlib.sha256(envelope.raw_payload_bytes).digest():
        return StoreOutcome.DUPLICATE
    cur.execute(
        """
        INSERT INTO bronze.raw_message_discrepancies (raw_message_id, received_payload_bytes, job_run_id)
        VALUES (%s, %s, %s)
        ON CONFLICT ON CONSTRAINT raw_message_discrepancies_payload_key DO NOTHING
        """,
        (raw_message_id, envelope.raw_payload_bytes, job_run_id),
    )
    return StoreOutcome.DISCREPANCY


def _active_mappings(cur: Cursor, envelope: MessageEnvelope) -> list[tuple[Any, Any]]:
    """Unrevoked staff confirmations for the message's exact source identity key."""
    if envelope.external_participant_id is None:
        return []
    cur.execute(
        """
        SELECT mapping_id, clinic_id FROM app.clinic_source_identities
        WHERE source_channel = %s AND source_account_id = %s AND external_participant_id = %s
          AND revoked_at IS NULL
        """,
        (envelope.source_channel, envelope.source_account_id, envelope.external_participant_id),
    )
    return cur.fetchall()


def _candidate_clinics(cur: Cursor, envelope: MessageEnvelope) -> list[Any]:
    """Clinics whose stored email equals the participant: candidate evidence only, never a link."""
    if envelope.external_participant_id is None:
        return []
    cur.execute(
        "SELECT clinic_id FROM app.clinics WHERE lower(btrim(email)) = %s",
        (envelope.external_participant_id,),
    )
    return [row[0] for row in cur.fetchall()]


def _insert_resolution(cur: Cursor, raw_message_id: Any, resolution: Resolution, job_run_id: str) -> None:
    """Current resolution plus its audit event, written together as the resolution tables require."""
    cur.execute(
        """
        INSERT INTO app.message_resolutions (raw_message_id, clinic_id, resolution_status, review_reason)
        VALUES (%s, %s, %s, %s)
        """,
        (raw_message_id, resolution.clinic_id, resolution.status, resolution.review_reason),
    )
    cur.execute(
        """
        INSERT INTO app.message_resolution_events (
            raw_message_id, mapping_id, old_clinic_id, new_clinic_id, old_status, new_status, reason, job_run_id
        )
        VALUES (%s, %s, NULL, %s, NULL, %s, %s, %s)
        """,
        (
            raw_message_id,
            resolution.mapping_id,
            resolution.clinic_id,
            resolution.status,
            resolution.review_reason or "confirmed_source_identity",
            job_run_id,
        ),
    )


def _open_inquiry(cur: Cursor, envelope: MessageEnvelope, raw_message_id: Any) -> bool:
    """Open an unknown-name inquiry unless one is already open for this source identity.

    The partial unique index allows one open inquiry per key, so later messages from the same first
    contact join that inquiry's conversation instead of creating more "Clinic name unknown" rows.
    The inquiry has no clinic name by design: only staff confirmation can supply it.
    """
    cur.execute(
        """
        INSERT INTO app.lead_inquiries (
            source_channel, source_account_id, external_participant_id, origin_raw_message_id, email
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (source_channel, source_account_id, external_participant_id)
            WHERE state = 'open' AND external_participant_id IS NOT NULL
            DO NOTHING
        RETURNING inquiry_id
        """,
        (
            envelope.source_channel,
            envelope.source_account_id,
            envelope.external_participant_id,
            raw_message_id,
            envelope.external_participant_id,
        ),
    )
    return cur.fetchone() is not None


def _jsonb_safe(value: Any) -> Any:
    """Remove NUL characters, which PostgreSQL jsonb cannot store; a stray NUL would fail the page."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {k: _jsonb_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonb_safe(v) for v in value]
    return value
