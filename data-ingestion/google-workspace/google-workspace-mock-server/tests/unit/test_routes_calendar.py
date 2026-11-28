"""Fake Calendar events.list: full sync, incremental sync with sync tokens, cancellations, paging and 410.

Seeded change numbers follow dataset order: 13 stored events (single events plus expanded occurrences), so the
calendar's counter is 13 after seeding. Scripted changes 2-5 reschedule the Reyes demo, cancel the Pena demo,
cancel one Northpoint occurrence and add the Tan demo.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mock_app import build_mock_google_app
from mock_dataset import read_dataset_or_problems
from mock_settings import MockServerSettings
from mock_state import MockGoogleState

SETTINGS = MockServerSettings(environment="ci", log_level="INFO", dataset_name="synthetic_soltech")
EVENTS = "/calendar/v3/calendars/primary/events"
AUTH = {"Authorization": "Bearer test-access-token"}
CANCELLED_OCCURRENCE = "evt-northpoint-golive-weekly_20261216T060000Z"


@pytest.fixture
def state() -> MockGoogleState:
    dataset, _ = read_dataset_or_problems(SETTINGS.dataset_path)
    return MockGoogleState(dataset, clock=lambda: dataset.seeded_at)


@pytest.fixture
def client(state) -> TestClient:
    return TestClient(build_mock_google_app(SETTINGS, state), headers=AUTH)


def sync_all_pages(client: TestClient, between_pages=None, **params) -> tuple[list[dict], str, int]:
    """Run one full or incremental sync to the end. Returns (items, nextSyncToken, number of pages).

    between_pages, if given, runs after the first page: a way to change the calendar mid-listing.
    """
    items, page_token, pages = [], None, 0
    while True:
        body = client.get(EVENTS, params={"singleEvents": "true", **params, "pageToken": page_token}).json()
        items += body["items"]
        pages += 1
        if pages == 1 and between_pages:
            between_pages()
        if "nextPageToken" not in body:
            assert "nextSyncToken" in body  # the last page, and only the last page, carries the sync token
            return items, body["nextSyncToken"], pages
        assert "nextSyncToken" not in body
        page_token = body["nextPageToken"]


def apply_scripted_changes(state: MockGoogleState, count: int) -> None:
    for _ in range(count):
        state.apply_next_scripted_change()


# --- access and request rules ---


def test_calendar_is_reached_as_primary_or_by_its_id_and_needs_a_token(client, state):
    by_id = client.get("/calendar/v3/calendars/sales@soltech.example.test/events", params={"singleEvents": "true"})
    unknown = client.get("/calendar/v3/calendars/other@example.test/events", params={"singleEvents": "true"})
    anonymous = TestClient(build_mock_google_app(SETTINGS, state)).get(EVENTS, params={"singleEvents": "true"})

    assert by_id.status_code == 200
    assert unknown.status_code == 404 and unknown.json()["error"]["errors"][0]["reason"] == "notFound"
    assert anonymous.status_code == 401


def test_single_events_is_required(client):
    response = client.get(EVENTS)

    assert response.status_code == 400 and "singleEvents" in response.json()["error"]["message"]


def test_filters_are_refused_together_with_a_sync_token(client):
    _, token, _ = sync_all_pages(client)

    response = client.get(
        EVENTS, params={"singleEvents": "true", "syncToken": token, "timeMin": "2026-12-01T00:00:00Z"}
    )

    assert response.status_code == 400 and "timeMin" in response.json()["error"]["message"]


def test_a_sync_token_the_mock_did_not_issue_is_a_400(client):
    response = client.get(EVENTS, params={"singleEvents": "true", "syncToken": "made-up"})

    assert response.status_code == 400


# --- full sync ---


def test_full_sync_lists_every_live_event_in_calendar_api_shape(client):
    items, _, _ = sync_all_pages(client)

    assert len(items) == 13
    first = items[0]
    assert first["kind"] == "calendar#event" and first["id"] == "evt-calendly-reyes-demo"
    assert first["start"] == {"dateTime": "2026-12-02T10:00:00+08:00", "timeZone": "Asia/Manila"}


def test_full_sync_hides_cancelled_events_unless_show_deleted(client, state):
    apply_scripted_changes(state, 4)  # ... up to and including cancelling the Pena demo

    live, _, _ = sync_all_pages(client)
    with_deleted, _, _ = sync_all_pages(client, showDeleted="true")

    assert "evt-calendly-pena-demo" not in {item["id"] for item in live}
    assert "evt-calendly-pena-demo" in {item["id"] for item in with_deleted}


def test_full_sync_pages_follow_next_page_token(client):
    paged, _, pages = sync_all_pages(client, maxResults=5)
    unpaged, _, _ = sync_all_pages(client)

    assert pages == 3 and [item["id"] for item in paged] == [item["id"] for item in unpaged]


def test_time_bounds_limit_a_full_sync(client):
    items, _, _ = sync_all_pages(client, timeMin="2027-01-01T00:00:00Z")

    assert {item["id"].rsplit("_", 1)[0] for item in items} == {"evt-villanueva-weekly-dst"} and len(items) == 3


def test_time_bound_without_an_offset_is_rejected(client):
    response = client.get(EVENTS, params={"singleEvents": "true", "timeMin": "2027-01-01T00:00:00"})

    assert response.status_code == 400


# --- incremental sync ---


def test_incremental_sync_returns_only_what_changed_since_the_token(client, state):
    _, token, _ = sync_all_pages(client)
    apply_scripted_changes(state, 6)  # reschedule, two cancellations and a new booking (plus two mail changes)

    changed, next_token, _ = sync_all_pages(client, syncToken=token)

    assert [item["id"] for item in changed] == [
        "evt-calendly-reyes-demo",
        "evt-calendly-pena-demo",
        CANCELLED_OCCURRENCE,
        "evt-calendly-tan-demo",
    ]
    assert changed[0]["start"]["dateTime"] == "2026-12-04T15:00:00+08:00" and changed[0]["sequence"] == 1
    assert next_token != token


def test_incremental_sync_with_nothing_new_is_empty_and_still_hands_out_a_token(client):
    _, token, _ = sync_all_pages(client)

    items, next_token, _ = sync_all_pages(client, syncToken=token)

    assert items == [] and next_token


def test_cancellations_come_back_in_googles_minimal_form(client, state):
    _, token, _ = sync_all_pages(client)
    apply_scripted_changes(state, 5)

    changed, _, _ = sync_all_pages(client, syncToken=token)
    by_id = {item["id"]: item for item in changed}

    cancelled_single = by_id["evt-calendly-pena-demo"]
    assert cancelled_single["status"] == "cancelled" and "summary" not in cancelled_single
    assert "attendees" not in cancelled_single and "start" not in cancelled_single
    occurrence = by_id[CANCELLED_OCCURRENCE]
    assert occurrence["recurringEventId"] == "evt-northpoint-golive-weekly"
    assert occurrence["originalStartTime"] == {"dateTime": "2026-12-16T14:00:00+08:00", "timeZone": "Asia/Manila"}


def test_an_expired_sync_token_is_a_410_full_sync_required(client, state):
    _, token, _ = sync_all_pages(client)
    state.calendar.oldest_valid_sync_position = state.calendar.change_counter + 1

    response = client.get(EVENTS, params={"singleEvents": "true", "syncToken": token})

    assert response.status_code == 410
    error = response.json()["error"]
    assert error["errors"][0]["reason"] == "fullSyncRequired" and "status" not in error  # Calendar's older style


# --- consistency while paging ---


def test_a_change_made_while_paging_is_never_lost_and_no_event_is_skipped(client, state):
    # Reschedule the Reyes demo AFTER page 1 (which already listed its old version) and before page 2.
    def reschedule_mid_listing():
        apply_scripted_changes(state, 3)

    first_pass, token, _ = sync_all_pages(client, between_pages=reschedule_mid_listing, maxResults=5)
    second_pass, _, _ = sync_all_pages(client, syncToken=token)

    # Every seeded event appears exactly once in the first pass: nothing shifted past a page boundary.
    assert len(first_pass) == len({item["id"] for item in first_pass}) == 13
    # The change made mid-listing arrives in the next sync instead of being lost.
    assert [item["id"] for item in second_pass] == ["evt-calendly-reyes-demo"]
    assert second_pass[0]["start"]["dateTime"] == "2026-12-04T15:00:00+08:00"
