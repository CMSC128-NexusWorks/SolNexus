"""`/_mock/*` controls, each checked through the Google-shaped API the way the master will see the change."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mock_app import build_mock_google_app
from mock_dataset import read_dataset_or_problems
from mock_oauth import MOCK_CLIENT_ID, MOCK_CLIENT_SECRET, MOCK_REFRESH_TOKEN
from mock_settings import MockServerSettings
from mock_state import MockGoogleState

SETTINGS = MockServerSettings(environment="ci", log_level="INFO", dataset_name="synthetic_soltech")
GMAIL = "/gmail/v1/users/me"
EVENTS = "/calendar/v3/calendars/primary/events"
VALID_GRANT = {
    "grant_type": "refresh_token",
    "client_id": MOCK_CLIENT_ID,
    "client_secret": MOCK_CLIENT_SECRET,
    "refresh_token": MOCK_REFRESH_TOKEN,
}
NEW_MESSAGE = {
    "id": "msg-new",
    "thread_id": "thr-new",
    "labels": ["INBOX"],
    "sent_at": "2026-11-22T10:00:00+08:00",
    "sender": "Clinic Owner <owner@newclinic.example.test>",
    "to": ["sales@soltech.example.test"],
    "subject": "Interested in your EMR",
    "body": "Hello, do you have a demo slot next week?",
}
NEW_BOOKING = {
    "id": "evt-new-booking",
    "summary": "SolTech Free 30-Minute Demo between SolTech Sales and Clinic Owner",
    "organizer": "sales@soltech.example.test",
    "attendees": [
        {"email": "sales@soltech.example.test", "response_status": "accepted"},
        {"email": "owner@newclinic.example.test", "response_status": "accepted"},
    ],
    "start": {"date_time": "2026-12-10T10:00:00", "time_zone": "Asia/Manila"},
    "end": {"date_time": "2026-12-10T10:30:00", "time_zone": "Asia/Manila"},
}


@pytest.fixture
def state() -> MockGoogleState:
    dataset, _ = read_dataset_or_problems(SETTINGS.dataset_path)
    return MockGoogleState(dataset, clock=lambda: dataset.seeded_at)


@pytest.fixture
def client(state) -> TestClient:
    """A client holding a real access token from the mock's token endpoint, as the master would."""
    client = TestClient(build_mock_google_app(SETTINGS, state))
    token = client.post("/token", data=VALID_GRANT).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def calendar_sync(client: TestClient, **params) -> dict:
    return client.get(EVENTS, params={"singleEvents": "true", **params}).json()


# --- Gmail data ---


def test_added_message_reaches_incremental_sync(client):
    start = client.get(f"{GMAIL}/profile").json()["historyId"]

    created = client.post("/_mock/gmail/messages", json=NEW_MESSAGE)
    history = client.get(f"{GMAIL}/history", params={"startHistoryId": start}).json()

    assert created.status_code == 201 and created.json()["success"] is True
    assert [r["messagesAdded"][0]["message"]["id"] for r in history["history"]] == ["msg-new"]


def test_duplicate_message_is_a_409_conflict(client):
    response = client.post("/_mock/gmail/messages", json={**NEW_MESSAGE, "id": "msg-001"})

    assert response.status_code == 409
    assert response.json()["error"] == "CONFLICT" and "msg-001" in response.json()["message"]


def test_message_with_an_unknown_field_is_refused_like_in_a_dataset(client):
    response = client.post("/_mock/gmail/messages", json={**NEW_MESSAGE, "subjct": "typo"})

    assert response.status_code == 422 and response.json()["error"] == "VALIDATION_FAILED"


def test_deleted_message_disappears_and_is_reported_as_deleted(client):
    start = client.get(f"{GMAIL}/profile").json()["historyId"]

    client.delete("/_mock/gmail/messages/msg-004")

    assert client.get(f"{GMAIL}/messages/msg-004", params={"format": "raw"}).status_code == 404
    history = client.get(f"{GMAIL}/history", params={"startHistoryId": start}).json()
    assert history["history"][0]["messagesDeleted"][0]["message"]["id"] == "msg-004"


def test_deleting_an_unknown_message_is_a_404(client):
    response = client.delete("/_mock/gmail/messages/msg-nope")

    assert response.status_code == 404 and response.json()["error"] == "NOT_FOUND"


def test_expired_history_forces_one_full_sync_then_incremental_sync_works_again(client):
    old_cursor = client.get(f"{GMAIL}/profile").json()["historyId"]  # what a client stored after its last sync

    client.post("/_mock/gmail/expire-history")
    gap = client.get(f"{GMAIL}/history", params={"startHistoryId": old_cursor})
    # The client's full resync: list everything, and take the profile's historyId as its new cursor.
    assert client.get(f"{GMAIL}/messages").status_code == 200
    new_cursor = client.get(f"{GMAIL}/profile").json()["historyId"]
    next_run = client.get(f"{GMAIL}/history", params={"startHistoryId": new_cursor})

    assert gap.status_code == 404
    # Regression: the fresh cursor must be accepted, or every later run would be another full resync.
    assert next_run.status_code == 200 and int(new_cursor) > int(old_cursor)


# --- Calendar data ---


def test_booking_moving_and_cancelling_reach_incremental_sync(client):
    token = calendar_sync(client)["nextSyncToken"]

    booked = client.post("/_mock/calendar/events", json=NEW_BOOKING)
    moved = client.post(
        "/_mock/calendar/events/evt-new-booking/reschedule",
        json={
            "start": {"date_time": "2026-12-11T15:00:00", "time_zone": "Asia/Manila"},
            "end": {"date_time": "2026-12-11T15:30:00", "time_zone": "Asia/Manila"},
        },
    )
    after_move = calendar_sync(client, syncToken=token)
    client.post("/_mock/calendar/events/evt-new-booking/cancel")
    after_cancel = calendar_sync(client, syncToken=after_move["nextSyncToken"])

    assert booked.json()["data"]["ids"] == ["evt-new-booking"] and moved.status_code == 200
    assert after_move["items"][0]["start"]["dateTime"] == "2026-12-11T15:00:00+08:00"
    assert after_cancel["items"] == [after_cancel["items"][0]] and after_cancel["items"][0]["status"] == "cancelled"


def test_cancelling_twice_is_a_409_and_an_unknown_event_a_404(client):
    client.post("/_mock/calendar/events/evt-calendly-pena-demo/cancel")

    assert client.post("/_mock/calendar/events/evt-calendly-pena-demo/cancel").status_code == 409
    assert client.post("/_mock/calendar/events/evt-nope/cancel").status_code == 404


def test_expired_sync_tokens_force_one_full_sync_then_incremental_sync_works_again(client):
    old_token = calendar_sync(client)["nextSyncToken"]

    client.post("/_mock/calendar/expire-sync-tokens")
    gone = client.get(EVENTS, params={"singleEvents": "true", "syncToken": old_token})
    new_token = calendar_sync(client)["nextSyncToken"]  # the client's full sync after the 410
    next_run = client.get(EVENTS, params={"singleEvents": "true", "syncToken": new_token})

    assert gone.status_code == 410
    # Regression: the full sync's token must be accepted, or every later run would 410 again.
    assert next_run.status_code == 200 and next_run.json()["items"] == []


# --- scripted changes, state and reset ---


def test_scripted_changes_apply_in_order_then_409(client):
    kinds = [client.post("/_mock/scripted-changes/next").json()["data"]["kind"] for _ in range(6)]
    exhausted = client.post("/_mock/scripted-changes/next")

    assert kinds[0] == "add_message" and kinds[-1] == "add_event"
    assert exhausted.status_code == 409


def test_state_summary_has_counts_and_cursors_only(client):
    summary = client.get("/_mock/state").json()["data"]

    assert summary["gmail"] == {
        "messages": 10,
        "current_history_id": 104010,
        "oldest_available_history_id": 104000,
    }
    assert summary["calendar"]["events"] == 13 and summary["oauth"]["issued_access_tokens"] == 1
    assert "@" not in str(summary)  # no addresses or content


def test_reset_restores_the_seed_and_drops_tokens_and_faults(client):
    client.post("/_mock/gmail/messages", json=NEW_MESSAGE)
    client.post("/_mock/faults", json={"target": "gmail", "kind": "backend_error", "times": 5})

    reset = client.post("/_mock/reset")

    assert reset.json()["data"]["gmail"]["messages"] == 10
    assert reset.json()["data"]["faults"]["scheduled"] == 0
    assert client.get(f"{GMAIL}/profile").status_code == 401  # tokens issued before the reset are gone


# --- OAuth ---


def test_revoked_consent_breaks_tokens_and_refresh(client):
    client.post("/_mock/oauth/revoke")

    assert client.get(f"{GMAIL}/profile").status_code == 401
    refresh = client.post("/token", data=VALID_GRANT)
    assert refresh.status_code == 400 and refresh.json()["error"] == "invalid_grant"


def test_expired_access_tokens_recover_with_a_refresh(client):
    client.post("/_mock/oauth/expire-access-tokens")

    assert client.get(f"{GMAIL}/profile").status_code == 401
    new_token = client.post("/token", data=VALID_GRANT).json()["access_token"]
    assert client.get(f"{GMAIL}/profile", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200


# --- faults and delays ---


def test_scheduled_fault_over_http_then_cleared(client):
    scheduled = client.post(
        "/_mock/faults", json={"target": "gmail", "kind": "rate_limit", "times": 1, "retry_after_seconds": 3}
    )
    listed = client.get("/_mock/faults").json()["data"]
    throttled = client.get(f"{GMAIL}/profile")
    recovered = client.get(f"{GMAIL}/profile")

    assert scheduled.status_code == 201 and listed["scheduled"][0]["kind"] == "rate_limit"
    assert throttled.status_code == 429 and throttled.headers["Retry-After"] == "3"
    assert recovered.status_code == 200


def test_fault_that_does_not_fit_its_target_is_a_422(client):
    response = client.post("/_mock/faults", json={"target": "token", "kind": "rate_limit"})

    assert response.status_code == 422 and "does not apply" in response.json()["message"]


def test_unknown_fault_kind_is_a_422(client):
    assert client.post("/_mock/faults", json={"target": "gmail", "kind": "meteor_strike"}).status_code == 422


def test_delays_are_set_listed_and_cleared(client):
    client.put("/_mock/delays/calendar", json={"delay_ms": 250})
    listed = client.get("/_mock/faults").json()["data"]["delay_ms"]

    client.delete("/_mock/faults")

    assert listed == {"gmail": 0, "calendar": 250, "token": 0}
    assert client.get("/_mock/faults").json()["data"]["delay_ms"]["calendar"] == 0


@pytest.mark.parametrize("delay_ms", [1001, 1003, 29_999])
def test_delays_are_reported_exactly_as_set(client, delay_ms):
    # Regression: reading the delay back through float seconds used to truncate, e.g. 1001 came back as 1000.
    client.put("/_mock/delays/gmail", json={"delay_ms": delay_ms})

    assert client.get("/_mock/faults").json()["data"]["delay_ms"]["gmail"] == delay_ms


def test_retry_after_with_a_non_throttling_fault_is_a_422(client):
    response = client.post(
        "/_mock/faults", json={"target": "calendar", "kind": "service_unavailable", "retry_after_seconds": 5}
    )

    assert response.status_code == 422 and "retry_after_seconds" in response.json()["message"]
