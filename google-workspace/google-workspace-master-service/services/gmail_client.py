"""Thin, read-only Gmail REST client: the four Gmail calls the connector needs.

Retries, OAuth and error classification come from google_api, shared with the Calendar client. This
module only knows Gmail's endpoints and what a 404 means for each of them.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import requests

from services.google_api import GoogleApi, GoogleApiError, GoogleNotFound, RetryPolicy, authorized_session

API_ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"
# Least privilege that can read message bodies (SNX-21 findings).
READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class HistoryExpired(GoogleApiError):
    """The stored historyId is too old for users.history.list; the caller must run a full sync."""


class GmailClient:
    def __init__(
        self,
        session: requests.Session,
        retry_policy: RetryPolicy = RetryPolicy(),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api = GoogleApi(session, API_ROOT, "Gmail", retry_policy, sleep)

    @classmethod
    def from_token_file(cls, token_path: str, **kwargs: Any) -> GmailClient:
        """Client for the mailbox whose OAuth token is at token_path (see google_api.authorized_session)."""
        return cls(authorized_session(token_path, [READONLY_SCOPE]), **kwargs)

    def get_profile(self) -> dict[str, Any]:
        """The connected mailbox's address and its current historyId."""
        return self._api.get("/profile")

    def list_message_ids(
        self, query: str | None, label_id: str | None, page_token: str | None
    ) -> tuple[list[str], str | None]:
        """One page of message IDs matching query/label (users.messages.list). Used for full syncs."""
        params = {"q": query, "labelIds": label_id, "pageToken": page_token, "maxResults": 100}
        body = self._api.get("/messages", params)
        return [m["id"] for m in body.get("messages", [])], body.get("nextPageToken")

    def list_history(
        self, start_history_id: str, label_id: str | None, page_token: str | None
    ) -> tuple[list[str], str | None, str]:
        """One page of IDs of messages added since start_history_id (users.history.list).

        Returns (message_ids, next_page_token, history_id). history_id is the mailbox's latest
        historyId, the cursor to store once every page has been written.
        """
        params = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "labelId": label_id,
            "pageToken": page_token,
            "maxResults": 500,
        }
        try:
            body = self._api.get("/history", params)
        except GoogleNotFound as exc:
            # Gmail keeps history for a limited time (typically about a week); 404 means the cursor
            # is older than that.
            raise HistoryExpired("stored historyId is no longer available") from exc

        ids: list[str] = []
        for record in body.get("history", []):
            for added in record.get("messagesAdded", []):
                message_id = added["message"]["id"]
                if message_id not in ids:  # one message can appear in several history records
                    ids.append(message_id)
        return ids, body.get("nextPageToken"), body["historyId"]

    def get_raw_message(self, message_id: str) -> dict[str, Any] | None:
        """The message in format=raw, or None if it was deleted after being listed."""
        try:
            return self._api.get(f"/messages/{message_id}", {"format": "raw"})
        except GoogleNotFound:
            return None
