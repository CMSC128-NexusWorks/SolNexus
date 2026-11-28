"""Connector checkpoints: the cursor each source resumes from, in app.ingestion_checkpoints.

One row per (source_channel, source_account_id). The cursor is opaque here: Gmail stores a historyId,
Calendar will store a sync token. Callers decide WHEN to save it; the rule every connector follows is
to save it in the same transaction as the last page it covers, so a crash can never move the cursor
past data that was not stored (see message_store.store_page).
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg2.extensions import connection as Connection
from psycopg2.extensions import cursor as Cursor


@dataclass(frozen=True)
class Checkpoint:
    source_channel: str
    source_account_id: str
    cursor_value: str


def save_checkpoint(cur: Cursor, checkpoint: Checkpoint) -> None:
    cur.execute(
        """
        INSERT INTO app.ingestion_checkpoints (source_channel, source_account_id, cursor_value)
        VALUES (%s, %s, %s)
        ON CONFLICT (source_channel, source_account_id) DO UPDATE SET cursor_value = EXCLUDED.cursor_value
        """,
        (checkpoint.source_channel, checkpoint.source_account_id, checkpoint.cursor_value),
    )


def load_checkpoint(conn: Connection, source_channel: str, source_account_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cursor_value FROM app.ingestion_checkpoints WHERE source_channel = %s AND source_account_id = %s",
            (source_channel, source_account_id),
        )
        row = cur.fetchone()
    conn.commit()  # end the read-only transaction so the connection does not sit "idle in transaction"
    return row[0] if row else None
