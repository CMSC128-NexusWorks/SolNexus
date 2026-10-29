"""Incremental Gmail sync for one mailbox: list -> fetch -> store, page by page.

Cursor: Gmail's historyId, stored in app.ingestion_checkpoints.

* No checkpoint yet: full sync of messages matching the backfill query. The mailbox historyId is read
  BEFORE listing, so mail arriving during the backfill is picked up by the next incremental run.
* Checkpoint present: users.history.list returns only messages added since that historyId.
* Checkpoint too old (Gmail drops history after about a week): fall back to a full sync. Replays are
  no-ops in bronze, so re-listing already stored mail is safe, only slower.

The checkpoint is written in the same transaction as the LAST page of a run. If a run dies midway,
the pages it committed stay (bronze dedupes them next time) and the next run restarts from the old
cursor, so no page is ever skipped.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass

from psycopg2.extensions import connection as Connection

from solnexus_ingest.envelope import MessageEnvelope
from solnexus_ingest.gmail.client import GmailClient, HistoryExpired
from solnexus_ingest.gmail.parsing import SOURCE_CHANNEL, canonical_address, parse_gmail_message, should_ingest
from solnexus_ingest.store import Checkpoint, load_checkpoint, store_page

log = logging.getLogger(__name__)

# Pages yield (message_ids, is_last_page, cursor_to_save_after_last_page).
PageSource = Iterator[tuple[list[str], bool, str]]


@dataclass(frozen=True)
class SyncSettings:
    # Optional Gmail label that marks lead-related mail (e.g. one applied by a Gmail filter). None
    # ingests the whole mailbox apart from drafts/spam/trash/chats. Applies to every run.
    label_id: str | None = None
    # Gmail search query bounding the FIRST (and any recovery) full sync, e.g. "newer_than:30d".
    # Incremental runs ignore it: the History API cannot filter by query.
    backfill_query: str | None = None


def sync_mailbox(
    client: GmailClient, conn: Connection, settings: SyncSettings, job_run_id: str
) -> dict[str, int | str]:
    """Bring bronze up to date with the mailbox. Returns counts only (safe for logs and XCom)."""
    profile = client.get_profile()
    account = canonical_address(profile["emailAddress"])
    cursor = load_checkpoint(conn, SOURCE_CHANNEL, account)

    if cursor is not None:
        try:
            # Materialize the first page now so an expired cursor is detected before anything is stored.
            pages = _history_pages(client, cursor, settings)
            first = next(pages)
            return _run(client, conn, account, _chain(first, pages), job_run_id, mode="incremental")
        except HistoryExpired:
            log.warning("Stored Gmail historyId expired; running a full resync")
            return _run(client, conn, account, _full_pages(client, profile["historyId"], settings), job_run_id,
                        mode="full_resync")

    return _run(client, conn, account, _full_pages(client, profile["historyId"], settings), job_run_id, mode="full")


# Every summary has all of these keys (0 when nothing happened), so monitoring can rely on its shape.
SUMMARY_COUNTS = (
    "pages",
    "inserted",
    "duplicate",
    "discrepancy",
    "inquiries_opened",
    "skipped_by_label",
    "deleted_before_fetch",
)


def _run(
    client: GmailClient, conn: Connection, account: str, pages: PageSource, job_run_id: str, mode: str
) -> dict[str, int | str]:
    counts: Counter[str] = Counter(dict.fromkeys(SUMMARY_COUNTS, 0))
    for message_ids, is_last, cursor in pages:
        envelopes = list(_fetch(client, account, message_ids, counts))
        checkpoint = Checkpoint(SOURCE_CHANNEL, account, cursor) if is_last else None
        counts.update(store_page(conn, envelopes, job_run_id, checkpoint))
        counts["pages"] += 1
    summary: dict[str, int | str] = {"mode": mode, **counts}
    log.info("Gmail sync finished: %s", summary)
    return summary


def _full_pages(client: GmailClient, start_history_id: str, settings: SyncSettings) -> PageSource:
    """messages.list pages; the cursor saved at the end is the historyId read before listing began."""
    page_token = None
    while True:
        ids, page_token = client.list_message_ids(settings.backfill_query, settings.label_id, page_token)
        yield ids, page_token is None, start_history_id
        if page_token is None:
            return


def _history_pages(client: GmailClient, start_history_id: str, settings: SyncSettings) -> PageSource:
    """history.list pages; the cursor saved at the end is the newest historyId Gmail reported."""
    page_token = None
    while True:
        ids, page_token, latest_history_id = client.list_history(start_history_id, settings.label_id, page_token)
        yield ids, page_token is None, latest_history_id
        if page_token is None:
            return


def _fetch(client: GmailClient, account: str, message_ids: list[str], counts: Counter[str]) -> Iterator[MessageEnvelope]:
    """Fetch and parse each listed message, counting the ones that are not stored and why."""
    for message_id in message_ids:
        message = client.get_raw_message(message_id)
        if message is None:
            counts["deleted_before_fetch"] += 1
        elif not should_ingest(message.get("labelIds")):
            counts["skipped_by_label"] += 1
        else:
            yield parse_gmail_message(message, account)


def _chain(first: tuple[list[str], bool, str], rest: PageSource) -> PageSource:
    yield first
    yield from rest
