"""Postgres-backed tests for the bronze writer: replay protection, resolution, inquiries, atomicity."""

from __future__ import annotations

import pytest

from solnexus_ingest.gmail.parsing import parse_gmail_message
from solnexus_ingest.store import Checkpoint, load_checkpoint, store_page
from tests.conftest import STAFF_USER_ID
from tests.gmail.messages import api_message, inbound, outbound, rfc822

RUN = "test-run"


def one(db, sql, params):
    with db.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    db.commit()
    return row


def message_state(db, parties, message_id):
    """(resolution_status, review_reason, clinic_id) for one stored message."""
    return one(
        db,
        """
        SELECT r.resolution_status, r.review_reason, r.clinic_id::text
        FROM bronze.raw_messages m JOIN app.message_resolutions r USING (raw_message_id)
        WHERE m.source_account_id = %s AND m.source_message_id = %s
        """,
        (parties.mailbox, message_id),
    )


def open_inquiries(db, parties):
    return one(
        db,
        "SELECT count(*) FROM app.lead_inquiries WHERE source_account_id = %s AND state = 'open'",
        (parties.mailbox,),
    )[0]


def add_clinic(db, email):
    return one(
        db,
        "INSERT INTO app.clinics (clinic_name, email, origin) VALUES ('Test Clinic', %s, 'manual') RETURNING clinic_id::text",
        (email,),
    )[0]


def confirm_mapping(db, parties, clinic_id):
    one(
        db,
        """
        INSERT INTO app.clinic_source_identities
            (source_channel, source_account_id, external_participant_id, clinic_id, confirmed_by)
        VALUES ('gmail', %s, %s, %s, %s) RETURNING mapping_id
        """,
        (parties.mailbox, parties.lead, clinic_id, STAFF_USER_ID),
    )


def test_replayed_page_is_stored_once(db, parties):
    page = [parse_gmail_message(inbound("m1", sender=parties.lead, mailbox=parties.mailbox), parties.mailbox)]

    first = store_page(db, page, RUN)
    second = store_page(db, page, RUN)

    assert first["inserted"] == 1
    assert second == {"duplicate": 1, "inquiries_opened": 0}
    assert one(db, "SELECT count(*) FROM bronze.raw_messages WHERE source_account_id = %s", (parties.mailbox,))[0] == 1


def test_replay_with_different_bytes_keeps_first_copy_and_records_discrepancy(db, parties):
    original = api_message("m1", rfc822(sender=parties.lead, to=parties.mailbox, body="first"))
    changed = api_message("m1", rfc822(sender=parties.lead, to=parties.mailbox, body="changed"))

    store_page(db, [parse_gmail_message(original, parties.mailbox)], RUN)
    counts = store_page(db, [parse_gmail_message(changed, parties.mailbox)], RUN)
    store_page(db, [parse_gmail_message(changed, parties.mailbox)], RUN)  # same differing copy again

    assert counts["discrepancy"] == 1
    stored = one(
        db,
        "SELECT convert_from(raw_payload_bytes, 'UTF8') FROM bronze.raw_messages WHERE source_account_id = %s",
        (parties.mailbox,),
    )[0]
    assert "first" in stored
    discrepancies = one(
        db,
        """
        SELECT count(*) FROM bronze.raw_message_discrepancies d JOIN bronze.raw_messages m USING (raw_message_id)
        WHERE m.source_account_id = %s
        """,
        (parties.mailbox,),
    )[0]
    assert discrepancies == 1


def test_first_contact_opens_one_unknown_name_inquiry_and_stays_unlinked(db, parties):
    page = [
        parse_gmail_message(inbound(f"m{n}", sender=parties.lead, mailbox=parties.mailbox), parties.mailbox)
        for n in range(2)
    ]

    counts = store_page(db, page, RUN)

    assert counts["inquiries_opened"] == 1
    assert open_inquiries(db, parties) == 1
    assert message_state(db, parties, "m0") == ("needs_review", "no_match", None)
    name_state, email = one(
        db,
        "SELECT clinic_name_state, email FROM app.lead_inquiries WHERE source_account_id = %s",
        (parties.mailbox,),
    )
    assert (name_state, email) == ("unknown", parties.lead)


def test_outbound_first_message_does_not_open_inquiry(db, parties):
    store_page(db, [parse_gmail_message(outbound("m1", to=parties.lead, mailbox=parties.mailbox), parties.mailbox)], RUN)

    assert open_inquiries(db, parties) == 0
    assert message_state(db, parties, "m1") == ("needs_review", "no_match", None)


def test_known_clinic_email_goes_to_review_without_inquiry(db, parties):
    add_clinic(db, parties.lead.upper())  # stored with different case on purpose

    store_page(db, [parse_gmail_message(inbound("m1", sender=parties.lead, mailbox=parties.mailbox), parties.mailbox)], RUN)

    assert message_state(db, parties, "m1") == ("needs_review", "unconfirmed_source_identity", None)
    assert open_inquiries(db, parties) == 0


def test_confirmed_mapping_links_and_audits_with_run_id(db, parties):
    clinic_id = add_clinic(db, None)
    confirm_mapping(db, parties, clinic_id)

    store_page(db, [parse_gmail_message(inbound("m1", sender=parties.lead, mailbox=parties.mailbox), parties.mailbox)], "run-42")

    assert message_state(db, parties, "m1") == ("linked", None, clinic_id)
    event = one(
        db,
        """
        SELECT e.old_status, e.new_status, e.new_clinic_id::text, e.job_run_id, e.mapping_id IS NOT NULL
        FROM app.message_resolution_events e JOIN bronze.raw_messages m USING (raw_message_id)
        WHERE m.source_account_id = %s
        """,
        (parties.mailbox,),
    )
    assert event == (None, "linked", clinic_id, "run-42", True)


def test_failed_page_rolls_back_messages_and_checkpoint(db, parties):
    good = parse_gmail_message(inbound("m1", sender=parties.lead, mailbox=parties.mailbox), parties.mailbox)
    checkpoint = Checkpoint("gmail", parties.mailbox, "999")

    class Boom(Exception):
        pass

    def page():
        yield good
        raise Boom  # e.g. the worker dies halfway through the page

    with pytest.raises(Boom):
        store_page(db, page(), RUN, checkpoint)

    assert one(db, "SELECT count(*) FROM bronze.raw_messages WHERE source_account_id = %s", (parties.mailbox,))[0] == 0
    assert load_checkpoint(db, "gmail", parties.mailbox) is None


def test_checkpoint_is_saved_with_the_page_and_updated_later(db, parties):
    store_page(db, [], RUN, Checkpoint("gmail", parties.mailbox, "100"))
    store_page(db, [], RUN, Checkpoint("gmail", parties.mailbox, "200"))

    assert load_checkpoint(db, "gmail", parties.mailbox) == "200"


def test_message_postgres_rejects_is_quarantined_and_page_still_commits(db, parties):
    good = parse_gmail_message(inbound("m-good", sender=parties.lead, mailbox=parties.mailbox), parties.mailbox)
    rejected = parse_gmail_message(inbound("m-bad", sender=parties.lead, mailbox=parties.mailbox), parties.mailbox)
    # jsonb cannot hold NUL characters, so PostgreSQL rejects this row with a DataError.
    rejected = type(rejected)(**{**rejected.__dict__, "source_recipient_ids": ("bad\x00id@example.test",)})

    counts = store_page(db, [rejected, good], RUN, Checkpoint("gmail", parties.mailbox, "500"))

    assert (counts["quarantined"], counts["inserted"]) == (1, 1)
    assert one(db, "SELECT count(*) FROM bronze.raw_messages WHERE source_account_id = %s", (parties.mailbox,))[0] == 1
    reason, has_payload = one(
        db,
        "SELECT reason, payload_bytes IS NOT NULL FROM bronze.quarantined_messages WHERE source_account_id = %s",
        (parties.mailbox,),
    )
    # psycopg2 reports the specific DataError subclass (here UntranslatableCharacter).
    assert reason.startswith("db_rejected:") and has_payload
    assert load_checkpoint(db, "gmail", parties.mailbox) == "500"
