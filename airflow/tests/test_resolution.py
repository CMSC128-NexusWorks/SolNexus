"""Unit tests for the initial resolution rules (identity contract outcomes)."""

import pytest

from solnexus_ingest.gmail.parsing import parse_gmail_message
from solnexus_ingest.resolution import decide, opens_inquiry
from tests.gmail.messages import MAILBOX, inbound, outbound

CLINIC_A, CLINIC_B, MAPPING = "clinic-a", "clinic-b", "mapping-1"


def envelope(message=None):
    return parse_gmail_message(message or inbound(), MAILBOX)


def test_one_active_mapping_links_the_message():
    resolution = decide(envelope(), [(MAPPING, CLINIC_A)], [])

    assert (resolution.status, resolution.clinic_id, resolution.mapping_id) == ("linked", CLINIC_A, MAPPING)
    assert resolution.review_reason is None


def test_matching_clinic_email_alone_never_links():
    resolution = decide(envelope(), [], [CLINIC_A])

    assert (resolution.status, resolution.review_reason) == ("needs_review", "unconfirmed_source_identity")
    assert resolution.clinic_id is None


@pytest.mark.parametrize(
    ("mappings", "candidates", "reason"),
    [
        ([], [], "no_match"),
        ([], [CLINIC_A, CLINIC_B], "multiple_candidates"),
        ([(MAPPING, CLINIC_A), ("mapping-2", CLINIC_B)], [], "multiple_confirmed_mappings"),
    ],
)
def test_review_reasons(mappings, candidates, reason):
    assert decide(envelope(), mappings, candidates).review_reason == reason


def test_message_without_single_participant_is_incomplete_even_if_mapped():
    raw_envelope = envelope()
    incomplete = type(raw_envelope)(**{**raw_envelope.__dict__, "external_participant_id": None})

    assert decide(incomplete, [(MAPPING, CLINIC_A)], []).review_reason == "incomplete_source_identity"


def test_only_inbound_unknown_contacts_open_an_inquiry():
    no_match = decide(envelope(), [], [])

    assert opens_inquiry(envelope(), no_match) is True
    assert opens_inquiry(envelope(outbound()), no_match) is False
    assert opens_inquiry(envelope(), decide(envelope(), [], [CLINIC_A])) is False
