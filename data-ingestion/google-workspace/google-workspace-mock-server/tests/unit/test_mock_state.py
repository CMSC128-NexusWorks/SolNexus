"""In-memory state: Gmail history, calendar versions, recurrence and time zones, scripted changes, reset."""

from __future__ import annotations

from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser

import pytest

from mock_dataset import read_dataset_or_problems
from mock_settings import DATASETS_DIR
from mock_state import MockGoogleState, MockStateError

FROZEN_NOW = datetime(2026, 11, 25, 3, 0, tzinfo=UTC)


@pytest.fixture
def state() -> MockGoogleState:
    dataset, _ = read_dataset_or_problems(DATASETS_DIR / "synthetic_soltech.json")
    return MockGoogleState(dataset, clock=lambda: FROZEN_NOW)


def apply_all_scripted_changes(state: MockGoogleState) -> None:
    while state.apply_next_scripted_change() is not None:
        pass


# --- Gmail ---


def test_seed_assigns_growing_history_ids_in_message_date_order(state):
    history_ids = [record.history_id for record in state.mailbox.history]

    assert history_ids == sorted(history_ids) and len(set(history_ids)) == len(history_ids)
    assert state.mailbox.current_history_id == history_ids[-1]
    assert state.mailbox.history[0].message_id == "msg-001"  # the earliest message


def test_raw_bytes_are_deterministic_and_parse_back_including_non_ascii_names(state):
    dataset = state.dataset
    again = MockGoogleState(dataset, clock=lambda: FROZEN_NOW)

    raw = state.mailbox.messages["msg-008"].raw_rfc822
    parsed = BytesParser(policy=policy.default).parsebytes(raw)

    assert raw == again.mailbox.messages["msg-008"].raw_rfc822  # same dataset, same bytes
    assert raw.isascii()  # non-ASCII is encoded on the wire, as in real mail
    assert "Peña" in str(parsed["From"]) and "Peña Pediatrics" in str(parsed["Subject"])
    assert b"\r\n" in raw


def test_reply_threads_to_the_original_message(state):
    parsed = BytesParser(policy=policy.default).parsebytes(state.mailbox.messages["msg-002"].raw_rfc822)

    assert parsed["In-Reply-To"] == "<msg-001@mock.example.test>"


def test_deleting_a_message_removes_it_and_records_a_newer_history_entry(state):
    before = state.mailbox.current_history_id

    state.mailbox.delete_message("msg-004")

    assert "msg-004" not in state.mailbox.messages
    last = state.mailbox.history[-1]
    assert (last.change, last.message_id, last.history_id) == ("messageDeleted", "msg-004", before + 1)
    with pytest.raises(MockStateError):
        state.mailbox.delete_message("msg-004")


# --- Calendar: recurrence and time zones ---


def test_weekly_series_is_stored_as_occurrences_with_google_style_ids(state):
    ids = sorted(i for i in state.calendar.events if i.startswith("evt-northpoint-golive-weekly_"))

    assert ids == [
        "evt-northpoint-golive-weekly_20261202T060000Z",
        "evt-northpoint-golive-weekly_20261209T060000Z",
        "evt-northpoint-golive-weekly_20261216T060000Z",
        "evt-northpoint-golive-weekly_20261223T060000Z",
    ]
    first = state.calendar.events[ids[0]].resource
    assert first["recurringEventId"] == "evt-northpoint-golive-weekly"
    assert first["originalStartTime"] == first["start"]
    ical_uids = {state.calendar.events[i].resource["iCalUID"] for i in ids}
    assert ical_uids == {"evt-northpoint-golive-weekly@mock.example.test"}
    assert "evt-northpoint-golive-weekly" not in state.calendar.events  # the series itself is never served


def test_weekly_series_keeps_local_time_across_a_daylight_saving_change(state):
    starts = [
        state.calendar.events[event_id].resource["start"]["dateTime"]
        for event_id in sorted(state.calendar.events)
        if event_id.startswith("evt-villanueva-weekly-dst_")
    ]

    # 17:00 every week in Los Angeles; the US switches to daylight time on 2027-03-14, so the offset changes
    # (and the Manila-side time moves from 09:00 to 08:00) while the local time stays put.
    assert starts == ["2027-03-04T17:00:00-08:00", "2027-03-11T17:00:00-08:00", "2027-03-18T17:00:00-07:00"]


def test_all_day_and_other_time_zone_events_render_like_google(state):
    site_visit = state.calendar.events["evt-northpoint-onboarding-day"].resource
    us_demo = state.calendar.events["evt-calendly-villanueva-demo"].resource

    assert site_visit["start"] == {"date": "2026-12-07"} and site_visit["end"] == {"date": "2026-12-08"}
    assert us_demo["start"] == {"dateTime": "2026-12-03T17:00:00-08:00", "timeZone": "America/Los_Angeles"}


def test_organizer_and_self_flags_appear_only_when_true(state):
    resource = state.calendar.events["evt-calendly-reyes-demo"].resource
    by_email = {attendee["email"]: attendee for attendee in resource["attendees"]}

    assert resource["organizer"] == {"email": "sales@soltech.example.test", "self": True}
    assert by_email["sales@soltech.example.test"].get("self") is True
    assert "self" not in by_email["ana.reyes@reyesfamilyclinic.example.test"]


# --- Calendar: versions ---


def test_every_write_gets_a_new_change_number_and_etag(state):
    numbers = [stored.change_number for stored in state.calendar.events.values()]
    etags = [stored.resource["etag"] for stored in state.calendar.events.values()]

    assert len(set(numbers)) == len(numbers) and max(numbers) == state.calendar.change_counter
    assert len(set(etags)) == len(etags)


def test_reschedule_writes_a_new_version_with_a_bumped_sequence(state):
    before = state.calendar.events["evt-calendly-reyes-demo"]

    state.apply_next_scripted_change()  # new mail
    state.apply_next_scripted_change()  # delete newsletter
    state.apply_next_scripted_change()  # reschedule the Reyes demo

    after = state.calendar.events["evt-calendly-reyes-demo"]
    assert after.change_number > before.change_number and after.resource["etag"] != before.resource["etag"]
    assert after.resource["sequence"] == before.resource["sequence"] + 1
    assert after.resource["start"]["dateTime"] == "2026-12-04T15:00:00+08:00"
    assert after.resource["updated"] == "2026-11-25T03:00:00.000Z"  # the injected clock, not the seed time
    assert before.resource["start"]["dateTime"] == "2026-12-02T10:00:00+08:00"  # old version left untouched


def test_cancelling_one_occurrence_leaves_the_rest_of_the_series(state):
    apply_all_scripted_changes(state)

    cancelled = state.calendar.events["evt-northpoint-golive-weekly_20261216T060000Z"].resource
    sibling = state.calendar.events["evt-northpoint-golive-weekly_20261209T060000Z"].resource
    assert cancelled["status"] == "cancelled" and sibling["status"] == "confirmed"
    with pytest.raises(MockStateError, match="already cancelled"):
        state.calendar.cancel_event("evt-northpoint-golive-weekly_20261216T060000Z", at=FROZEN_NOW)


# --- Scripted changes and reset ---


def test_scripted_changes_run_in_order_then_stop(state):
    kinds = []
    while (change := state.apply_next_scripted_change()) is not None:
        kinds.append(change.kind)

    assert kinds == [
        "add_message",
        "delete_message",
        "reschedule_event",
        "cancel_event",
        "cancel_event",
        "add_event",
    ]
    assert "msg-011" in state.mailbox.messages and "evt-calendly-tan-demo" in state.calendar.events


def test_reset_returns_to_the_seed_and_rewinds_scripted_changes(state):
    seeded_history_id = state.mailbox.current_history_id
    seeded_counter = state.calendar.change_counter
    apply_all_scripted_changes(state)

    state.reset()

    assert state.mailbox.current_history_id == seeded_history_id and "msg-004" in state.mailbox.messages
    assert state.calendar.change_counter == seeded_counter
    assert state.calendar.events["evt-calendly-pena-demo"].resource["status"] == "confirmed"
    assert state.next_scripted_change_index == 0


def test_default_clock_starts_at_seeded_at_and_moves_forward():
    # Relative Gmail queries (newer_than:30d) are measured from this clock, so it must start at the dataset's
    # seed time, not today's date, and still advance so later changes get later timestamps.
    dataset, _ = read_dataset_or_problems(DATASETS_DIR / "synthetic_soltech.json")
    state = MockGoogleState(dataset)

    first, second = state.clock(), state.clock()

    assert dataset.seeded_at <= first <= second
    assert (first - dataset.seeded_at).total_seconds() < 60
