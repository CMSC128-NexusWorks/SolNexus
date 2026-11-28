"""`/_mock/*` control routes: change the fake Google while it runs, from tests, demos or a terminal.

These are the levers for everything the pipeline has to survive: new mail arriving, mail being deleted, meetings
booked, moved and cancelled, cursors expiring (Gmail history gap, Calendar 410), consent being revoked, access
tokens expiring, throttling, outages and slow responses. They are not part of Google's API, so they live under
`/_mock` and answer in the mock's own envelope:

    success: {"success": true, "data": {...}}
    error:   {"success": false, "error": "NOT_FOUND", "message": "...", "status": 404}

Request bodies reuse the dataset schema (mock_dataset), so a message or event sent here is validated exactly like
one in a dataset file, unknown fields included. The routes have no authentication of their own: the mock holds only
synthetic data, runs only in local, ci and dev, and Compose binds it to localhost.
"""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from mock_dataset import DatasetEvent, DatasetEventTime, DatasetMessage
from mock_faults import FAULT_TARGETS, FaultKind, FaultTarget, ScheduledFault
from mock_state import MockGoogleState, MockStateError

router = APIRouter(prefix="/_mock")


class StrictBody(BaseModel):
    """Request bodies reject unknown fields, so a typo is a 422 instead of a silently ignored setting."""

    model_config = ConfigDict(extra="forbid")


class RescheduleBody(StrictBody):
    start: DatasetEventTime
    end: DatasetEventTime


class ScheduleFaultBody(StrictBody):
    target: FaultTarget
    kind: FaultKind
    # How many upcoming requests to that target fail.
    times: int = Field(default=1, ge=1, le=1000)
    # Sent as Retry-After with the throttling kinds (rate_limit, user_rate_limit); a 422 with any other kind.
    retry_after_seconds: int | None = Field(default=None, ge=1, le=3600)


class DelayBody(StrictBody):
    delay_ms: int = Field(ge=0, le=30_000)


def mock_state(request: Request) -> MockGoogleState:
    return request.app.state.mock_google_state


def ok(data: dict[str, Any]) -> dict[str, Any]:
    """The success envelope shared by every control route."""
    return {"success": True, "data": data}


def raise_for_state_error(exc: MockStateError) -> NoReturn:
    """Turn a refused change into the envelope's 404 or 409 (HTTPException is rendered by mock_app's handlers)."""
    raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


# --- whole-mock controls ---


@router.post("/reset")
def reset_to_seed(request: Request) -> dict[str, Any]:
    """Back to the dataset seed: data, cursors, scripted changes, issued tokens, revocation, faults and delays."""
    state = mock_state(request)
    state.reset()
    return ok(summarize_state(state))


@router.post("/scripted-changes/next")
def apply_next_scripted_change(request: Request) -> dict[str, Any]:
    """Apply the dataset's next scripted change, in order. 409 once all of them have been applied (until reset)."""
    state = mock_state(request)
    with state.lock:
        index = state.next_scripted_change_index
        try:
            change = state.apply_next_scripted_change()
        except MockStateError as exc:
            raise_for_state_error(exc)
        if change is None:
            raise HTTPException(status_code=409, detail="all scripted changes have been applied; reset to replay")
        remaining = len(state.dataset.scripted_changes) - state.next_scripted_change_index
    return ok({"applied_index": index, "kind": change.kind, "remaining": remaining})


@router.get("/state")
def get_state_summary(request: Request) -> dict[str, Any]:
    """Counts and cursor positions only (no message or event content), for tests to assert on."""
    return ok(summarize_state(mock_state(request)))


def summarize_state(state: MockGoogleState) -> dict[str, Any]:
    with state.lock:
        return {
            "dataset": state.dataset.description[:60],
            "gmail": {
                "messages": len(state.mailbox.messages),
                "current_history_id": state.mailbox.current_history_id,
                "oldest_available_history_id": state.mailbox.oldest_available_history_id,
            },
            "calendar": {
                "events": len(state.calendar.events),
                "change_counter": state.calendar.change_counter,
                "oldest_valid_sync_position": state.calendar.oldest_valid_sync_position,
            },
            "scripted_changes": {
                "applied": state.next_scripted_change_index,
                "total": len(state.dataset.scripted_changes),
            },
            "oauth": {
                "issued_access_tokens": len(state.oauth.issued),
                "refresh_token_revoked": state.oauth.refresh_token_revoked,
            },
            "faults": {"scheduled": len(state.faults.scheduled)},
        }


# --- Gmail data ---


@router.post("/gmail/messages", status_code=201)
def add_gmail_message(message: DatasetMessage, request: Request) -> dict[str, Any]:
    """New mail arrives: stored with the next historyId, so incremental sync picks it up."""
    state = mock_state(request)
    with state.lock:
        try:
            stored = state.mailbox.add_message(message)
        except MockStateError as exc:
            raise_for_state_error(exc)
    return ok({"id": stored.message_id, "history_id": stored.history_id})


@router.delete("/gmail/messages/{message_id}")
def delete_gmail_message(message_id: str, request: Request) -> dict[str, Any]:
    """Mail is permanently deleted: gone from messages.get, reported by history.list as messagesDeleted."""
    state = mock_state(request)
    with state.lock:
        try:
            state.mailbox.delete_message(message_id)
        except MockStateError as exc:
            raise_for_state_error(exc)
        history_id = state.mailbox.current_history_id
    return ok({"id": message_id, "history_id": history_id})


@router.post("/gmail/expire-history")
def expire_gmail_history(request: Request) -> dict[str, Any]:
    """Make every history cursor handed out so far too old (a "history gap").

    Even a client that synced a moment ago gets 404 from history.list and must fall back to a full sync, the recovery
    path this exists to test. The cursor that full sync then stores is valid, so the client returns to incremental
    sync afterwards (see MockGmailMailbox.expire_history_handed_out_so_far).
    """
    state = mock_state(request)
    with state.lock:
        boundary = state.mailbox.expire_history_handed_out_so_far()
    return ok({"oldest_available_history_id": boundary})


# --- Calendar data ---


@router.post("/calendar/events", status_code=201)
def add_calendar_event(event: DatasetEvent, request: Request) -> dict[str, Any]:
    """A meeting is booked (as Calendly would). A series is stored as its occurrences, like the dataset's."""
    state = mock_state(request)
    with state.lock:
        try:
            stored_ids = state.calendar.add_event(event, at=state.clock())
        except MockStateError as exc:
            raise_for_state_error(exc)
    return ok({"ids": stored_ids})


@router.post("/calendar/events/{event_id}/reschedule")
def reschedule_calendar_event(event_id: str, body: RescheduleBody, request: Request) -> dict[str, Any]:
    """A meeting (or one occurrence) moves: a new version with a new etag and sequence + 1."""
    state = mock_state(request)
    with state.lock:
        try:
            state.calendar.reschedule_event(event_id, body.start, body.end, at=state.clock())
        except MockStateError as exc:
            raise_for_state_error(exc)
        etag = state.calendar.events[event_id].resource["etag"]
    return ok({"id": event_id, "etag": etag})


@router.post("/calendar/events/{event_id}/cancel")
def cancel_calendar_event(event_id: str, request: Request) -> dict[str, Any]:
    """A meeting (or one occurrence) is cancelled: incremental sync reports it as status "cancelled"."""
    state = mock_state(request)
    with state.lock:
        try:
            state.calendar.cancel_event(event_id, at=state.clock())
        except MockStateError as exc:
            raise_for_state_error(exc)
    return ok({"id": event_id, "status": "cancelled"})


@router.post("/calendar/expire-sync-tokens")
def expire_calendar_sync_tokens(request: Request) -> dict[str, Any]:
    """Make every sync token handed out so far expired: the next incremental sync gets 410 fullSyncRequired.

    The full sync the client then runs hands out a valid token, so it returns to incremental sync afterwards (see
    MockGoogleCalendar.expire_sync_tokens_handed_out_so_far).
    """
    state = mock_state(request)
    with state.lock:
        boundary = state.calendar.expire_sync_tokens_handed_out_so_far()
    return ok({"oldest_valid_sync_position": boundary})


# --- OAuth ---


@router.post("/oauth/revoke")
def revoke_consent(request: Request) -> dict[str, Any]:
    """The user revokes SolNexus's access: issued tokens stop working and every refresh is invalid_grant.

    That is the "a person must re-authorize" case: the master should fail the run visibly instead of retrying.
    Only reset() restores access, as only a new consent would with Google.
    """
    state = mock_state(request)
    with state.lock:
        state.oauth.refresh_token_revoked = True
        state.oauth.issued.clear()
    return ok({"refresh_token_revoked": True})


@router.post("/oauth/expire-access-tokens")
def expire_access_tokens(request: Request) -> dict[str, Any]:
    """Every issued access token expires now. Clients get 401, refresh, and carry on (the refresh token still works)."""
    state = mock_state(request)
    with state.lock:
        expired = len(state.oauth.issued)
        state.oauth.issued.clear()
    return ok({"expired_access_tokens": expired})


# --- Faults and delays ---


@router.get("/faults")
def list_faults(request: Request) -> dict[str, Any]:
    state = mock_state(request)
    with state.lock:
        return ok(
            {
                "scheduled": [
                    {
                        "target": f.target,
                        "kind": f.kind,
                        "remaining": f.remaining,
                        "retry_after_seconds": f.retry_after_seconds,
                    }
                    for f in state.faults.scheduled
                ],
                "delay_ms": {target: state.faults.delay_ms_for(target) for target in FAULT_TARGETS},
            }
        )


@router.post("/faults", status_code=201)
def schedule_fault(body: ScheduleFaultBody, request: Request) -> dict[str, Any]:
    """The next `times` requests to `target` fail with `kind`. A kind that does not fit the target is a 422."""
    state = mock_state(request)
    with state.lock:
        try:
            state.faults.schedule(ScheduledFault(body.target, body.kind, body.times, body.retry_after_seconds))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        scheduled = len(state.faults.scheduled)
    return ok({"scheduled": scheduled})


@router.delete("/faults")
def clear_faults_and_delays(request: Request) -> dict[str, Any]:
    """Drop every scheduled fault and per-target delay (the startup default delay stays)."""
    state = mock_state(request)
    with state.lock:
        state.faults.scheduled.clear()
        state.faults.delay_ms_by_target.clear()
    return ok({"scheduled": 0})


@router.put("/delays/{target}")
def set_delay(target: FaultTarget, body: DelayBody, request: Request) -> dict[str, Any]:
    """Every request to `target` waits `delay_ms` before being answered (0 = no delay)."""
    state = mock_state(request)
    with state.lock:
        state.faults.delay_ms_by_target[target] = body.delay_ms
    return ok({"target": target, "delay_ms": body.delay_ms})
