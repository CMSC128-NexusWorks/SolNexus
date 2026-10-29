"""Unit tests for Gmail message parsing: direction, participant identity, times and payload."""

from datetime import datetime, timezone

import pytest

from solnexus_ingest.gmail.parsing import parse_gmail_message, should_ingest
from tests.gmail.messages import LEAD, MAILBOX, api_message, inbound, outbound, rfc822


def test_inbound_message_uses_sender_as_participant():
    envelope = parse_gmail_message(inbound(), MAILBOX)

    assert envelope.direction == "inbound"
    assert envelope.external_participant_id == LEAD
    assert envelope.source_sender_id == LEAD
    assert envelope.source_recipient_ids == (MAILBOX,)
    assert envelope.source_account_id == MAILBOX
    assert envelope.source_message_id == "m-in-1"
    assert envelope.source_thread_id == "thread-1"


def test_outbound_message_uses_single_recipient_as_participant():
    envelope = parse_gmail_message(outbound(), MAILBOX)

    assert envelope.direction == "outbound"
    assert envelope.external_participant_id == LEAD
    assert envelope.source_sender_id == MAILBOX


def test_message_from_mailbox_is_outbound_even_without_sent_label():
    envelope = parse_gmail_message(outbound(labels=("INBOX",)), MAILBOX)

    assert envelope.direction == "outbound"


def test_participant_is_canonical_but_original_spelling_is_kept():
    envelope = parse_gmail_message(inbound(sender="Lead@Clinic.Example.TEST"), MAILBOX)

    assert envelope.external_participant_id == LEAD
    assert envelope.source_sender_id == "Lead@Clinic.Example.TEST"


def test_outbound_to_several_clinic_addresses_has_no_single_participant():
    raw = rfc822(sender=MAILBOX, to=LEAD, cc="other@clinic2.example.test")

    envelope = parse_gmail_message(api_message("m-2", raw, labels=("SENT",)), MAILBOX)

    # Ambiguous: resolution must send this to review as an incomplete source identity.
    assert envelope.external_participant_id is None
    assert set(envelope.source_recipient_ids) == {LEAD, "other@clinic2.example.test"}


def test_copying_our_own_mailbox_does_not_make_the_participant_ambiguous():
    raw = rfc822(sender=MAILBOX, to=LEAD, cc=MAILBOX)

    envelope = parse_gmail_message(api_message("m-3", raw, labels=("SENT",)), MAILBOX)

    assert envelope.external_participant_id == LEAD


def test_event_time_comes_from_internal_date_in_utc():
    envelope = parse_gmail_message(inbound(), MAILBOX)

    assert envelope.source_event_at == datetime(2026, 10, 25, 2, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("internal_date", [None, "not-a-number"])
def test_missing_or_invalid_event_time_stays_null(internal_date):
    envelope = parse_gmail_message(inbound(internal_date_ms=internal_date), MAILBOX)

    # Never replaced with ingestion time (data contract).
    assert envelope.source_event_at is None


def test_raw_payload_is_the_exact_rfc822_bytes():
    raw = rfc822(sender=LEAD, to=MAILBOX)

    envelope = parse_gmail_message(api_message("m-4", raw), MAILBOX)

    assert envelope.raw_payload_bytes == raw


def test_parsed_payload_holds_subject_text_and_parser_version():
    envelope = parse_gmail_message(inbound(), MAILBOX)

    assert envelope.parsed_payload["parser_version"] == "gmail-raw-v1"
    assert envelope.parsed_payload["subject"] == "Question about SolTech EMR"
    assert envelope.parsed_payload["text_plain"].strip() == "Hello, we would like a demo."
    assert envelope.parsed_payload["label_ids"] == ["INBOX"]


@pytest.mark.parametrize(
    ("labels", "expected"),
    [(["INBOX"], True), (["SENT"], True), (["DRAFT"], False), (["SPAM"], False), (["TRASH"], False), (None, True)],
)
def test_should_ingest_skips_drafts_spam_and_trash(labels, expected):
    assert should_ingest(labels) is expected
