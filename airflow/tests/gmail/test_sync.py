"""Postgres-backed tests for the sync loop, using an in-memory fake Gmail mailbox."""

from __future__ import annotations

import pytest

from solnexus_ingest.gmail.client import GmailRetriesExhausted, HistoryExpired
from solnexus_ingest.gmail.sync import SyncSettings, sync_mailbox
from solnexus_ingest.store import load_checkpoint
from tests.gmail.messages import api_message, inbound, outbound, rfc822

RUN = "test-run"


class FakeMailbox:
    """Implements the GmailClient methods sync_mailbox uses, over an in-memory mailbox.

    page_size makes multi-page listings; fail_on_list_call injects a failure on that call number;
    history_expired simulates Gmail having dropped the stored cursor.
    """

    def __init__(self, address: str, page_size: int = 2):
        self.address = address
        self.page_size = page_size
        self.messages: dict[str, dict] = {}
        self.history_id = 100
        self.added_since: dict[int, list[str]] = {}  # history_id at add time -> ids
        self.fail_on_list_call: int | None = None
        self.history_expired = False
        self.list_calls = 0
        self.fetched: list[str] = []
        self.queries: list[tuple] = []

    def add(self, message: dict) -> None:
        self.messages[message["id"]] = message
        self.added_since.setdefault(self.history_id, []).append(message["id"])
        self.history_id += 1

    def get_profile(self):
        return {"emailAddress": self.address, "historyId": str(self.history_id)}

    def list_message_ids(self, query, label_id, page_token):
        self.queries.append(("list", query, label_id))
        return self._page(list(self.messages), page_token)

    def list_history(self, start_history_id, label_id, page_token):
        if self.history_expired:
            raise HistoryExpired("expired")
        self.queries.append(("history", start_history_id, label_id))
        ids = [i for h, batch in sorted(self.added_since.items()) if h >= int(start_history_id) for i in batch]
        page, next_token = self._page(ids, page_token)
        return page, next_token, str(self.history_id)

    def get_raw_message(self, message_id):
        self.fetched.append(message_id)
        return self.messages.get(message_id)

    def _page(self, ids, page_token):
        self.list_calls += 1
        if self.list_calls == self.fail_on_list_call:
            raise GmailRetriesExhausted("injected failure")
        start = int(page_token or 0)
        end = start + self.page_size
        return ids[start:end], (str(end) if end < len(ids) else None)


def stored_ids(db, mailbox):
    with db.cursor() as cur:
        cur.execute(
            "SELECT source_message_id FROM bronze.raw_messages WHERE source_account_id = %s ORDER BY 1",
            (mailbox,),
        )
        rows = [r[0] for r in cur.fetchall()]
    db.commit()
    return rows


@pytest.fixture
def mailbox(parties):
    box = FakeMailbox(parties.mailbox)
    box.add(inbound("m1", sender=parties.lead, mailbox=parties.mailbox))
    box.add(outbound("m2", to=parties.lead, mailbox=parties.mailbox))
    box.add(inbound("m3", sender=parties.lead, mailbox=parties.mailbox))
    return box


def test_first_run_is_a_full_sync_that_saves_the_starting_history_id(db, parties, mailbox):
    summary = sync_mailbox(mailbox, db, SyncSettings(backfill_query="newer_than:30d"), RUN)

    assert summary["mode"] == "full"
    assert summary["inserted"] == 3 and summary["pages"] == 2
    assert stored_ids(db, parties.mailbox) == ["m1", "m2", "m3"]
    assert load_checkpoint(db, "gmail", parties.mailbox) == "103"
    assert mailbox.queries[0] == ("list", "newer_than:30d", None)


def test_next_run_reads_only_new_history(db, parties, mailbox):
    sync_mailbox(mailbox, db, SyncSettings(), RUN)
    mailbox.add(inbound("m4", sender=parties.lead, mailbox=parties.mailbox))

    summary = sync_mailbox(mailbox, db, SyncSettings(), RUN)

    assert summary["mode"] == "incremental"
    assert (summary["inserted"], summary["duplicate"]) == (1, 0)
    assert mailbox.queries[-1] == ("history", "103", None)
    assert load_checkpoint(db, "gmail", parties.mailbox) == "104"


def test_rerun_with_nothing_new_changes_nothing(db, parties, mailbox):
    sync_mailbox(mailbox, db, SyncSettings(), RUN)

    summary = sync_mailbox(mailbox, db, SyncSettings(), RUN)

    assert summary["mode"] == "incremental"
    assert {k: v for k, v in summary.items() if k != "mode" and v} == {"pages": 1}
    assert stored_ids(db, parties.mailbox) == ["m1", "m2", "m3"]


def test_failure_mid_run_keeps_committed_pages_and_old_checkpoint(db, parties, mailbox):
    mailbox.fail_on_list_call = 2  # first page stored, then listing page 2 fails

    with pytest.raises(GmailRetriesExhausted):
        sync_mailbox(mailbox, db, SyncSettings(), RUN)

    assert stored_ids(db, parties.mailbox) == ["m1", "m2"]
    assert load_checkpoint(db, "gmail", parties.mailbox) is None  # the uncommitted page is not skipped

    mailbox.fail_on_list_call = None
    summary = sync_mailbox(mailbox, db, SyncSettings(), RUN)

    assert stored_ids(db, parties.mailbox) == ["m1", "m2", "m3"]
    assert (summary["inserted"], summary["already_stored"]) == (1, 2)
    assert mailbox.fetched[-1:] == ["m3"]  # the two committed messages were not downloaded again
    assert load_checkpoint(db, "gmail", parties.mailbox) == "103"


def test_expired_cursor_falls_back_to_full_resync_without_duplicates(db, parties, mailbox):
    sync_mailbox(mailbox, db, SyncSettings(), RUN)
    mailbox.add(inbound("m4", sender=parties.lead, mailbox=parties.mailbox))
    mailbox.history_expired = True

    summary = sync_mailbox(mailbox, db, SyncSettings(), RUN)

    assert summary["mode"] == "full_resync"
    assert (summary["inserted"], summary["already_stored"], summary["duplicate"]) == (1, 3, 0)
    assert mailbox.fetched[-1:] == ["m4"]  # the resync downloaded only the new message
    assert load_checkpoint(db, "gmail", parties.mailbox) == "104"


def test_drafts_and_deleted_messages_are_counted_not_stored(db, parties, mailbox):
    mailbox.add(api_message("draft", rfc822(sender=parties.mailbox, to=parties.lead), labels=("DRAFT",)))
    mailbox.added_since[mailbox.history_id] = ["gone"]  # listed, then deleted before fetch
    mailbox.history_id += 1

    summary = sync_mailbox(mailbox, db, SyncSettings(), RUN)
    summary2 = sync_mailbox(mailbox, db, SyncSettings(), RUN)

    assert summary["skipped_by_label"] == 1
    assert "draft" not in stored_ids(db, parties.mailbox)
    assert summary2["mode"] == "incremental"


def test_label_filter_is_passed_to_both_listing_calls(db, parties, mailbox):
    settings = SyncSettings(label_id="Label_SolNexus")

    sync_mailbox(mailbox, db, settings, RUN)
    sync_mailbox(mailbox, db, settings, RUN)

    assert mailbox.queries[0] == ("list", None, "Label_SolNexus")
    assert mailbox.queries[-1] == ("history", "103", "Label_SolNexus")


def test_summary_contains_no_addresses(db, parties, mailbox):
    summary = sync_mailbox(mailbox, db, SyncSettings(), RUN)

    assert "example.test" not in repr(summary)


def test_unparseable_message_is_quarantined_and_cursor_moves_on(db, parties, mailbox):
    mailbox.add({"id": "broken-base64", "threadId": "t", "labelIds": ["INBOX"], "raw": "!!not base64!!"})
    mailbox.add({"id": "no-raw-field", "threadId": "t", "labelIds": ["INBOX"]})

    first = sync_mailbox(mailbox, db, SyncSettings(), RUN)
    second = sync_mailbox(mailbox, db, SyncSettings(), RUN)

    assert (first["quarantined"], first["inserted"]) == (2, 3)
    assert load_checkpoint(db, "gmail", parties.mailbox) == "105"  # not stuck behind the bad messages
    assert second["mode"] == "incremental" and second["quarantined"] == 0
    with db.cursor() as cur:
        cur.execute(
            "SELECT source_message_id, reason FROM bronze.quarantined_messages WHERE source_account_id = %s ORDER BY 1",
            (parties.mailbox,),
        )
        rows = cur.fetchall()
    db.commit()
    assert rows[0][0] == "broken-base64" and rows[0][1].startswith("parse_error:")
    assert rows[1] == ("no-raw-field", "parse_error:KeyError")
