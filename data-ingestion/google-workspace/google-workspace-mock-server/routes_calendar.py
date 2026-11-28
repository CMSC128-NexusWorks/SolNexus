"""Fake Google Calendar API v3: events.list with full and incremental (sync token) synchronization.

    GET /calendar/v3/calendars/{calendarId}/events
        singleEvents=true (required), syncToken, pageToken, maxResults, showDeleted, timeMin, timeMax

The calendar contract (docs/contracts/google-calendar-v1.md) has the master sync this way:
1. **Full sync:** list without a syncToken, following nextPageToken; the LAST page carries nextSyncToken.
2. **Incremental sync:** list with that syncToken; only events changed since come back, cancellations included, and
   the last page carries the next syncToken.
3. **Expired token:** 410 fullSyncRequired; the client starts over with a full sync.

How the mock implements it: a sync token is a position on the calendar's change counter (mock_state). A listing
captures the counter value when its first page is requested (the "snapshot") and every page, plus the final
nextSyncToken, is pinned to that snapshot. An event changed while a client is still paging therefore is not mixed
into this listing; it arrives in the next incremental sync. Nothing is lost, at worst something is delivered twice,
which the master's bronze layer absorbs (etag-keyed replay protection).

Pages use keyset pagination, not offsets: a page token stores the change number of the last event listed, and the
next page starts after it. With offsets, an event changing mid-paging would drop out of the snapshot-filtered list,
shift every later event down one position, and the next page would silently skip one. Keys cannot shift.

Deliberate limits, failing loudly (400): singleEvents must be true, because the mock stores only expanded
occurrences, exactly what the contract asks for.
"""

from __future__ import annotations

import copy
from datetime import datetime, time
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request

from google_errors import GoogleApiError
from mock_oauth import require_access_token_for
from mock_paging import decode_opaque_token, encode_opaque_token
from mock_state import MockGoogleCalendar, MockGoogleState, StoredCalendarEvent, format_google_timestamp

router = APIRouter(
    prefix="/calendar/v3/calendars/{calendar_id}",
    dependencies=[
        # The access token must be one the mock issued, unexpired, with a Calendar scope.
        Depends(require_access_token_for("calendar")),
    ],
)

SYNC_TOKEN_KIND = "calendar-sync"
PAGE_TOKEN_KIND = "calendar-page"
# Stored in a page token when the listing is a full sync (there is no "changed after" position).
FULL_SYNC_MARKER = -1


def mock_state(request: Request) -> MockGoogleState:
    return request.app.state.mock_google_state


def calendar_for_id(state: MockGoogleState, calendar_id: str) -> MockGoogleCalendar:
    """The calendar for `primary` or its own ID (the account address). Any other calendar is unknown."""
    if calendar_id not in ("primary", state.calendar.calendar_id):
        raise GoogleApiError(404, "notFound", "Not Found")
    return state.calendar


def event_as_listed(stored: StoredCalendarEvent) -> dict[str, Any]:
    """The event as events.list returns it.

    A cancelled event comes back in Google's minimal form: id, status, etag and, for one cancelled occurrence of a
    series, recurringEventId and originalStartTime (how a client knows which slot was removed). Title, attendees and
    times are not repeated. The mock also sends `updated`; Google guarantees only id and status for deleted events,
    so the master must not depend on more than that.
    """
    resource = stored.resource
    if resource["status"] != "cancelled":
        return copy.deepcopy(resource)
    minimal = {key: resource[key] for key in ("kind", "etag", "id", "status", "updated")}
    for series_key in ("recurringEventId", "originalStartTime"):
        if series_key in resource:
            minimal[series_key] = copy.deepcopy(resource[series_key])
    return minimal


def event_time_as_instant(event_time: dict[str, str], calendar_time_zone: str) -> datetime:
    """A start/end as an aware datetime. An all-day date counts from midnight in the calendar's time zone."""
    if "dateTime" in event_time:
        return datetime.fromisoformat(event_time["dateTime"])
    day = datetime.fromisoformat(event_time["date"]).date()
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(calendar_time_zone))


def parse_rfc3339_bound(value: str | None, parameter: str) -> datetime | None:
    """timeMin / timeMax: an RFC 3339 timestamp WITH an offset (Google rejects one without)."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        raise GoogleApiError(400, "badRequest", f"Bad Request: {parameter} must be an RFC 3339 timestamp with offset.")
    return parsed


@router.get("/events")
def list_events(
    calendar_id: str,
    request: Request,
    single_events: Annotated[bool, Query(alias="singleEvents")] = False,
    sync_token: Annotated[str | None, Query(alias="syncToken")] = None,
    page_token: Annotated[str | None, Query(alias="pageToken")] = None,
    max_results: Annotated[int, Query(alias="maxResults", ge=1, le=2500)] = 250,
    show_deleted: Annotated[bool, Query(alias="showDeleted")] = False,
    time_min: Annotated[str | None, Query(alias="timeMin")] = None,
    time_max: Annotated[str | None, Query(alias="timeMax")] = None,
    order_by: Annotated[str | None, Query(alias="orderBy")] = None,
    q: str | None = None,
    updated_min: Annotated[str | None, Query(alias="updatedMin")] = None,
) -> dict[str, Any]:
    """events.list. Full sync without syncToken, incremental with it; see the module docstring for the protocol."""
    if not single_events:
        raise GoogleApiError(400, "invalid", "The mock supports only singleEvents=true (expanded occurrences).")
    incompatible = {"timeMin": time_min, "timeMax": time_max, "orderBy": order_by, "q": q, "updatedMin": updated_min}
    if sync_token and any(value is not None for value in incompatible.values()):
        # Google refuses these filters on an incremental sync: the token alone defines what is returned.
        used = ", ".join(name for name, value in incompatible.items() if value is not None)
        raise GoogleApiError(400, "invalid", f"Parameters incompatible with syncToken: {used}.")
    lower_bound = parse_rfc3339_bound(time_min, "timeMin")
    upper_bound = parse_rfc3339_bound(time_max, "timeMax")

    state = mock_state(request)
    with state.lock:
        calendar = calendar_for_id(state, calendar_id)

        if page_token:
            # A later page of a listing already in progress: reuse its snapshot and "changed after" position.
            page_context = decode_opaque_token(page_token, PAGE_TOKEN_KIND)
            if page_context is None:
                raise GoogleApiError(400, "invalid", "Invalid pageToken value.")
            listed_up_to, snapshot = page_context["listed_up_to"], page_context["snapshot"]
            changed_after = None if page_context["changed_after"] == FULL_SYNC_MARKER else page_context["changed_after"]
        else:
            # First page: nothing listed yet, and the snapshot is the counter right now.
            listed_up_to, snapshot = 0, calendar.change_counter
            changed_after = None
            if sync_token:
                token_payload = decode_opaque_token(sync_token, SYNC_TOKEN_KIND)
                if token_payload is None:
                    raise GoogleApiError(400, "invalid", "Invalid syncToken value.")
                changed_after = token_payload["position"]
                listed_up_to = changed_after

        if changed_after is not None and changed_after < calendar.oldest_valid_sync_position:
            raise GoogleApiError(410, "fullSyncRequired", "Sync token is no longer valid, a full sync is required.")

        # Only versions written after the last listed key and up to the snapshot belong on this page.
        candidates = [stored for stored in calendar.events.values() if listed_up_to < stored.change_number <= snapshot]
        if changed_after is not None:
            # Incremental: everything changed since the token, cancellations included (showDeleted is implied).
            candidates = [stored for stored in candidates if stored.change_number > changed_after]
        else:
            if not show_deleted:
                candidates = [stored for stored in candidates if stored.resource["status"] != "cancelled"]
            if lower_bound or upper_bound:
                candidates = [
                    stored
                    for stored in candidates
                    if (
                        lower_bound is None
                        or event_time_as_instant(stored.resource["end"], calendar.time_zone) > lower_bound
                    )
                    and (
                        upper_bound is None
                        or event_time_as_instant(stored.resource["start"], calendar.time_zone) < upper_bound
                    )
                ]
        # Change order: deterministic, and the order the changes happened in.
        candidates.sort(key=lambda stored: stored.change_number)
        page = candidates[:max_results]
        has_more = len(candidates) > max_results

        body: dict[str, Any] = {
            "kind": "calendar#events",
            "etag": f'"{snapshot:016d}"',
            "summary": calendar.calendar_id,
            "updated": format_google_timestamp(state.clock()),
            "timeZone": calendar.time_zone,
            "accessRole": "owner",
            "defaultReminders": [],
            "items": [event_as_listed(stored) for stored in page],
        }
    if has_more:
        body["nextPageToken"] = encode_opaque_token(
            PAGE_TOKEN_KIND,
            {
                "listed_up_to": page[-1].change_number,
                "snapshot": snapshot,
                "changed_after": FULL_SYNC_MARKER if changed_after is None else changed_after,
            },
        )
    else:
        # Only the last page carries the next sync token, pinned to the snapshot the listing started from.
        body["nextSyncToken"] = encode_opaque_token(SYNC_TOKEN_KIND, {"position": snapshot})
    return body
