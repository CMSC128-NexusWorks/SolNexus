"""Fake Gmail API v1: the four calls the master makes, at Google's own paths and in Google's own shapes.

    GET /gmail/v1/users/{userId}/profile
    GET /gmail/v1/users/{userId}/messages             (q, labelIds, includeSpamTrash, pageToken, maxResults)
    GET /gmail/v1/users/{userId}/messages/{id}        (format=raw | minimal)
    GET /gmail/v1/users/{userId}/history              (startHistoryId, historyTypes, labelId, pageToken, maxResults)

Point the master's Gmail client at `http://<mock>/gmail/v1/users/me` instead of
`https://gmail.googleapis.com/gmail/v1/users/me` and nothing else changes. Like Gmail, history IDs and internalDate
are JSON strings, messages are listed newest first, and every call needs a bearer token.

Deliberate limits, each failing loudly (400) rather than silently returning wrong data:
- `q` supports only `newer_than:` and `older_than:` (with d, m or y), the operators the master's backfill query uses.
- `format` supports only `raw` (what the master fetches) and `minimal`.
"""

from __future__ import annotations

import base64
import re
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from google_errors import GoogleApiError
from mock_auth import require_bearer_token
from mock_paging import slice_page
from mock_state import GmailHistoryRecord, MockGmailMailbox, MockGoogleState, StoredGmailMessage

router = APIRouter(prefix="/gmail/v1/users/{user_id}", dependencies=[Depends(require_bearer_token)])

# Gmail leaves spam and trash out of messages.list unless includeSpamTrash=true.
LABELS_HIDDEN_FROM_LIST_BY_DEFAULT = frozenset({"SPAM", "TRASH"})
# `newer_than:7d` style terms; Gmail's units are days, months and years.
RELATIVE_AGE_TERM = re.compile(r"^(newer_than|older_than):([1-9][0-9]*)([dmy])$")
DAYS_PER_UNIT = {"d": 1, "m": 30, "y": 365}
ALL_HISTORY_TYPES = frozenset({"messageAdded", "messageDeleted", "labelAdded", "labelRemoved"})
# The record key Gmail uses for each change type (note the plural "messages", not "message" + "s").
HISTORY_RECORD_KEY_BY_CHANGE = {"messageAdded": "messagesAdded", "messageDeleted": "messagesDeleted"}


def mock_state(request: Request) -> MockGoogleState:
    return request.app.state.mock_google_state


def mailbox_for_user(state: MockGoogleState, user_id: str) -> MockGmailMailbox:
    """The mailbox for `me` or the mailbox's own address. Anyone else is refused, as Gmail refuses access to
    another user's mailbox without domain-wide delegation."""
    if user_id not in ("me", state.mailbox.address):
        raise GoogleApiError(403, "forbidden", f"Delegation denied for {state.mailbox.address}")
    return state.mailbox


def matches_search_query(message: StoredGmailMessage, query: str | None, now_ms: int) -> bool:
    """Whether a message matches a Gmail search query (only newer_than/older_than terms, all of which must hold)."""
    for term in (query or "").split():
        match = RELATIVE_AGE_TERM.match(term)
        if match is None:
            raise GoogleApiError(
                400,
                "invalidArgument",
                f"The mock supports only newer_than: and older_than: in q, got {term!r}.",
            )
        operator, amount, unit = match.group(1), int(match.group(2)), match.group(3)
        boundary_ms = now_ms - int(timedelta(days=amount * DAYS_PER_UNIT[unit]).total_seconds() * 1000)
        if operator == "newer_than" and message.internal_date_ms < boundary_ms:
            return False
        if operator == "older_than" and message.internal_date_ms >= boundary_ms:
            return False
    return True


def history_record_json(record: GmailHistoryRecord) -> dict[str, Any]:
    """One history record in Gmail's shape: the message, plus the change it went through."""
    message_ref = {"id": record.message_id, "threadId": record.thread_id}
    return {
        "id": str(record.history_id),
        "messages": [message_ref],
        HISTORY_RECORD_KEY_BY_CHANGE[record.change]: [{"message": {**message_ref, "labelIds": list(record.label_ids)}}],
    }


@router.get("/profile")
def get_profile(user_id: str, request: Request) -> dict[str, Any]:
    """users.getProfile: the mailbox address and its current historyId (the cursor a full sync starts from)."""
    state = mock_state(request)
    with state.lock:
        mailbox = mailbox_for_user(state, user_id)
        return {
            "emailAddress": mailbox.address,
            "messagesTotal": len(mailbox.messages),
            "threadsTotal": len({m.thread_id for m in mailbox.messages.values()}),
            "historyId": str(mailbox.current_history_id),
        }


@router.get("/messages")
def list_messages(
    user_id: str,
    request: Request,
    q: str | None = None,
    label_ids: Annotated[list[str] | None, Query(alias="labelIds")] = None,
    include_spam_trash: Annotated[bool, Query(alias="includeSpamTrash")] = False,
    page_token: Annotated[str | None, Query(alias="pageToken")] = None,
    max_results: Annotated[int, Query(alias="maxResults", ge=1, le=500)] = 100,
) -> dict[str, Any]:
    """users.messages.list: IDs of matching messages, newest first, one page at a time."""
    state = mock_state(request)
    with state.lock:
        mailbox = mailbox_for_user(state, user_id)
        now_ms = int(state.clock().timestamp() * 1000)
        matching = [
            message
            for message in mailbox.messages.values()
            # Every requested label must be present (Gmail ANDs repeated labelIds).
            if set(label_ids or ()) <= set(message.label_ids)
            and (include_spam_trash or not LABELS_HIDDEN_FROM_LIST_BY_DEFAULT & set(message.label_ids))
            and matches_search_query(message, q, now_ms)
        ]
        # Newest first, like Gmail; the ID breaks ties so paging order is stable.
        matching.sort(key=lambda m: (-m.internal_date_ms, m.message_id))
        page, next_token = slice_page(matching, page_token, max_results)

    body: dict[str, Any] = {
        "messages": [{"id": m.message_id, "threadId": m.thread_id} for m in page],
        "resultSizeEstimate": len(matching),
    }
    if not page:
        del body["messages"]  # Gmail omits the key entirely when nothing matches
    if next_token:
        body["nextPageToken"] = next_token
    return body


@router.get("/messages/{message_id}")
def get_message(
    user_id: str,
    message_id: str,
    request: Request,
    message_format: Annotated[str, Query(alias="format")] = "full",
) -> dict[str, Any]:
    """users.messages.get. `raw` returns the RFC 822 bytes base64url-encoded; a deleted message is a 404."""
    if message_format not in ("raw", "minimal"):
        raise GoogleApiError(
            400, "invalidArgument", f"The mock supports format=raw or minimal, got {message_format!r}."
        )
    state = mock_state(request)
    with state.lock:
        message = mailbox_for_user(state, user_id).messages.get(message_id)
        if message is None:
            raise GoogleApiError(404, "notFound", "Requested entity was not found.")
        body: dict[str, Any] = {
            "id": message.message_id,
            "threadId": message.thread_id,
            "labelIds": list(message.label_ids),
            "snippet": message.snippet,
            "historyId": str(message.history_id),
            "internalDate": str(message.internal_date_ms),
            "sizeEstimate": message.size_estimate,
        }
    if message_format == "raw":
        # base64url without "=" padding: Gmail may omit padding, and the master's decoder is built to cope.
        body["raw"] = base64.urlsafe_b64encode(message.raw_rfc822).decode().rstrip("=")
    return body


@router.get("/history")
def list_history(
    user_id: str,
    request: Request,
    start_history_id: Annotated[str, Query(alias="startHistoryId")],
    history_types: Annotated[list[str] | None, Query(alias="historyTypes")] = None,
    label_id: Annotated[str | None, Query(alias="labelId")] = None,
    page_token: Annotated[str | None, Query(alias="pageToken")] = None,
    max_results: Annotated[int, Query(alias="maxResults", ge=1, le=500)] = 100,
) -> dict[str, Any]:
    """users.history.list: mailbox changes after startHistoryId, plus the mailbox's latest historyId.

    A startHistoryId older than the retained history is a 404, which is how Gmail says "history gap, run a full
    sync". The response's top-level historyId is what the client stores as its next cursor.
    """
    if not start_history_id.isdigit():
        raise GoogleApiError(400, "invalidArgument", "Invalid startHistoryId.")
    unknown_types = set(history_types or ()) - ALL_HISTORY_TYPES
    if unknown_types:
        raise GoogleApiError(400, "invalidArgument", f"Invalid historyTypes: {', '.join(sorted(unknown_types))}.")
    wanted_types = set(history_types or ()) or ALL_HISTORY_TYPES
    start = int(start_history_id)

    state = mock_state(request)
    with state.lock:
        mailbox = mailbox_for_user(state, user_id)
        if start < mailbox.oldest_available_history_id:
            raise GoogleApiError(404, "notFound", "Requested entity was not found.")
        records = [
            record
            for record in mailbox.history
            if record.history_id > start
            and record.change in wanted_types
            and (label_id is None or label_id in record.label_ids)
        ]
        page, next_token = slice_page(records, page_token, max_results)
        latest_history_id = mailbox.current_history_id

    body: dict[str, Any] = {"historyId": str(latest_history_id)}
    if page:
        body["history"] = [history_record_json(record) for record in page]
    if next_token:
        body["nextPageToken"] = next_token
    return body
