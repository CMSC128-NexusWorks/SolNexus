"""Fake Gmail API: Google's paths, shapes and errors, exercised in-process with the mock clock frozen at seeded_at.

Seeded history (dataset messages in date order): msg-001 -> 104001, msg-002 -> 104002, ..., msg-010 -> 104010.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from mock_app import build_mock_google_app
from mock_dataset import read_dataset_or_problems
from mock_settings import MockServerSettings
from mock_state import MockGoogleState

SETTINGS = MockServerSettings(environment="ci", log_level="INFO", dataset_name="synthetic_soltech")
GMAIL = "/gmail/v1/users/me"
AUTH = {"Authorization": "Bearer test-access-token"}


@pytest.fixture
def state() -> MockGoogleState:
    dataset, _ = read_dataset_or_problems(SETTINGS.dataset_path)
    # Frozen at 2026-11-20T00:00Z, so newer_than/older_than results never depend on when the test runs.
    return MockGoogleState(dataset, clock=lambda: dataset.seeded_at)


@pytest.fixture
def client(state) -> TestClient:
    return TestClient(build_mock_google_app(SETTINGS, state), headers=AUTH)


def list_all_message_ids(client: TestClient, **params) -> list[str]:
    """Follow nextPageToken to the end, as the master does."""
    ids, page_token = [], None
    while True:
        body = client.get(f"{GMAIL}/messages", params={**params, "pageToken": page_token}).json()
        ids += [m["id"] for m in body.get("messages", [])]
        page_token = body.get("nextPageToken")
        if page_token is None:
            return ids


# --- auth, users and errors ---


def test_every_call_needs_a_bearer_token_and_fails_in_googles_format(state):
    anonymous = TestClient(build_mock_google_app(SETTINGS, state))

    response = anonymous.get(f"{GMAIL}/profile")

    assert response.status_code == 401
    error = response.json()["error"]
    assert (error["code"], error["errors"][0]["reason"], error["status"]) == (401, "authError", "UNAUTHENTICATED")


def test_another_users_mailbox_is_refused_but_the_own_address_works(client):
    assert client.get("/gmail/v1/users/someone@else.example.test/profile").status_code == 403
    assert client.get("/gmail/v1/users/sales@soltech.example.test/profile").status_code == 200


def test_unknown_gmail_path_is_a_google_404_while_mock_paths_keep_the_envelope(client):
    google_style = client.get(f"{GMAIL}/drafts").json()
    envelope = client.get("/_mock/nothing").json()

    assert google_style["error"]["errors"][0]["reason"] == "notFound"
    assert envelope["error"] == "NOT_FOUND" and envelope["success"] is False


def test_bad_query_parameter_is_a_400_invalid_argument_not_a_422(client):
    response = client.get(f"{GMAIL}/messages", params={"maxResults": 0})

    assert response.status_code == 400
    assert response.json()["error"]["errors"][0]["reason"] == "invalidArgument"


# --- profile ---


def test_profile_returns_address_and_current_history_id_as_a_string(client):
    body = client.get(f"{GMAIL}/profile").json()

    assert body["emailAddress"] == "sales@soltech.example.test"
    assert body["historyId"] == "104010"
    assert body["messagesTotal"] == 10


# --- messages.list ---


def test_list_is_newest_first_and_hides_spam_unless_asked(client):
    default_ids = list_all_message_ids(client)
    with_spam = list_all_message_ids(client, includeSpamTrash="true")

    assert default_ids[0] == "msg-010" and default_ids[-1] == "msg-001"
    assert "msg-006" not in default_ids and "msg-006" in with_spam
    assert "msg-005" in default_ids  # drafts are listed; skipping them is the master's job


def test_paging_walks_every_message_exactly_once(client):
    paged = list_all_message_ids(client, maxResults=3)

    assert paged == list_all_message_ids(client) and len(paged) == len(set(paged)) == 9


def test_label_filter_requires_every_label(client):
    assert list_all_message_ids(client, labelIds=["INBOX", "UNREAD"]) == ["msg-003"]


def test_relative_age_query_is_measured_from_the_mock_clock(client):
    # Mock "now" is 2026-11-20T00:00Z, so 2 days back is 2026-11-18T00:00Z.
    newer = list_all_message_ids(client, q="newer_than:2d")
    older = list_all_message_ids(client, q="older_than:2d")

    assert set(older) == {"msg-001", "msg-002"}
    assert set(newer).isdisjoint(older) and len(newer) + len(older) == 9


def test_unsupported_query_operator_fails_loudly(client):
    response = client.get(f"{GMAIL}/messages", params={"q": "from:ana.reyes@reyesfamilyclinic.example.test"})

    assert response.status_code == 400
    assert "newer_than" in response.json()["error"]["message"]


def test_empty_result_omits_the_messages_key_like_gmail(client):
    body = client.get(f"{GMAIL}/messages", params={"labelIds": "NO_SUCH_LABEL"}).json()

    assert "messages" not in body and body["resultSizeEstimate"] == 0


def test_a_page_token_the_mock_did_not_issue_is_a_400(client):
    assert client.get(f"{GMAIL}/messages", params={"pageToken": "not-a-token"}).status_code == 400


# --- messages.get ---


def test_raw_format_returns_the_exact_rfc822_bytes_base64url_encoded(client, state):
    body = client.get(f"{GMAIL}/messages/msg-008", params={"format": "raw"}).json()

    raw = body["raw"]
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    assert decoded == state.mailbox.messages["msg-008"].raw_rfc822
    assert "=" not in raw  # unpadded, as Gmail may send it
    assert body["internalDate"].isdigit() and body["historyId"] == "104008"
    assert body["labelIds"] == ["INBOX"] and body["snippet"].startswith("Magandang araw po!")


def test_minimal_format_has_no_raw_and_other_formats_are_refused(client):
    assert "raw" not in client.get(f"{GMAIL}/messages/msg-001", params={"format": "minimal"}).json()
    assert client.get(f"{GMAIL}/messages/msg-001", params={"format": "full"}).status_code == 400


def test_unknown_and_deleted_messages_are_google_404s(client, state):
    state.mailbox.delete_message("msg-004")

    for message_id in ("msg-404", "msg-004"):
        response = client.get(f"{GMAIL}/messages/{message_id}", params={"format": "raw"})
        assert response.status_code == 404
        assert response.json()["error"]["errors"][0]["reason"] == "notFound"


# --- history.list ---


def test_history_returns_changes_after_the_start_and_the_latest_history_id(client):
    body = client.get(f"{GMAIL}/history", params={"startHistoryId": "104008"}).json()

    assert body["historyId"] == "104010"
    assert [record["id"] for record in body["history"]] == ["104009", "104010"]
    added = body["history"][0]["messagesAdded"][0]["message"]
    assert added == {"id": "msg-009", "threadId": "thr-001", "labelIds": ["INBOX"]}


def test_history_reports_deletions_and_filters_by_type_and_label(client, state):
    state.mailbox.delete_message("msg-004")

    deleted = client.get(f"{GMAIL}/history", params={"startHistoryId": "104010", "historyTypes": "messageDeleted"})
    added_only = client.get(f"{GMAIL}/history", params={"startHistoryId": "104010", "historyTypes": "messageAdded"})
    sent_label = client.get(f"{GMAIL}/history", params={"startHistoryId": "104000", "labelId": "SENT"})

    assert deleted.json()["history"][0]["messagesDeleted"][0]["message"]["id"] == "msg-004"
    assert "history" not in added_only.json()  # nothing matched: key omitted, historyId still present
    assert [r["messages"][0]["id"] for r in sent_label.json()["history"]] == ["msg-002"]


def test_history_pages_follow_next_page_token(client):
    first = client.get(f"{GMAIL}/history", params={"startHistoryId": "104000", "maxResults": 4}).json()
    second = client.get(
        f"{GMAIL}/history", params={"startHistoryId": "104000", "maxResults": 4, "pageToken": first["nextPageToken"]}
    ).json()

    assert [r["id"] for r in first["history"]] == ["104001", "104002", "104003", "104004"]
    assert second["history"][0]["id"] == "104005"


def test_start_before_the_retained_history_is_a_404_history_gap(client, state):
    state.mailbox.oldest_available_history_id = 104005

    gap = client.get(f"{GMAIL}/history", params={"startHistoryId": "104004"})
    still_retained = client.get(f"{GMAIL}/history", params={"startHistoryId": "104005"})

    assert gap.status_code == 404 and gap.json()["error"]["errors"][0]["reason"] == "notFound"
    assert still_retained.status_code == 200


def test_non_numeric_start_history_id_is_a_400(client):
    assert client.get(f"{GMAIL}/history", params={"startHistoryId": "abc"}).status_code == 400
