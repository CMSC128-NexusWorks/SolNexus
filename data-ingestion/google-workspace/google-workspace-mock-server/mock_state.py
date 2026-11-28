"""In-memory state of the fake Google: one Gmail mailbox and one calendar, seeded from a dataset.

The state models the two things incremental sync depends on, the same way Google does:

- **Gmail history.** Every mailbox change gets the next, ever-growing `historyId` and a history record
  (messageAdded / messageDeleted). The master's incremental sync asks "what changed since historyId N".
- **Calendar versions.** Every calendar change bumps one change counter. The stored event remembers the
  counter value it was written at, and gets a new `etag` and `updated` time. Sync tokens (step 4) are just
  positions on that counter: "everything written after position N".

Nothing is persisted: a restart or reset() returns to the dataset's seed, which keeps tests repeatable.
"""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email import policy
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from mock_dataset import (
    SUPPORTED_RECURRENCE,
    AddEventChange,
    AddMessageChange,
    CancelEventChange,
    DatasetEvent,
    DatasetEventTime,
    DatasetMessage,
    DeleteMessageChange,
    MockDataset,
    RescheduleEventChange,
    ScriptedChange,
)
from mock_faults import FaultPlan
from mock_oauth import DEFAULT_GRANTED_SCOPES, MockOAuthServer
from mock_settings import StartupProblem

# Domain used for generated Message-IDs and iCalUIDs, so nothing the mock invents can look like real mail.
MOCK_ID_DOMAIN = "mock.example.test"


class MockStateError(Exception):
    """A change that cannot be applied, e.g. deleting a message that does not exist."""


def format_google_timestamp(moment: datetime) -> str:
    """RFC 3339 in UTC with milliseconds and a Z, the way Google writes `created` and `updated`."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# --- Gmail ---------------------------------------------------------------------------------------------


def render_rfc822_bytes(message: DatasetMessage) -> bytes:
    """The message as RFC 822 bytes: what Gmail returns, base64url-encoded, for `format=raw`.

    Rendering is deterministic (same dataset, same bytes, every time). That matters because the master
    treats a replayed message whose bytes differ as a discrepancy; a mock that re-rendered differently on
    each request would trigger false discrepancies. The SMTP policy gives CRLF line endings, like real mail,
    and encodes non-ASCII headers (e.g. "Pena" with a tilde) as RFC 2047 encoded-words.
    """
    email = EmailMessage(policy=policy.SMTP)
    email["From"] = message.sender
    email["To"] = ", ".join(message.to)
    if message.cc:
        email["Cc"] = ", ".join(message.cc)
    email["Subject"] = message.subject
    email["Date"] = format_datetime(message.sent_at)
    email["Message-ID"] = f"<{message.id}@{MOCK_ID_DOMAIN}>"
    if message.in_reply_to:
        # Both headers, as mail clients set them, so threading looks real.
        email["In-Reply-To"] = f"<{message.in_reply_to}@{MOCK_ID_DOMAIN}>"
        email["References"] = f"<{message.in_reply_to}@{MOCK_ID_DOMAIN}>"
    email.set_content(message.body)
    return email.as_bytes()


@dataclass(frozen=True)
class StoredGmailMessage:
    """A message currently in the mailbox, with the fields the Gmail API exposes."""

    message_id: str
    thread_id: str
    label_ids: tuple[str, ...]
    # Gmail's internalDate: milliseconds since the epoch, from the message's Date.
    internal_date_ms: int
    raw_rfc822: bytes
    # The historyId at which the message was added.
    history_id: int
    # Gmail's short plain-text preview of the body, and its size estimate in bytes.
    snippet: str
    size_estimate: int


@dataclass(frozen=True)
class GmailHistoryRecord:
    """One mailbox change, as users.history.list reports it."""

    history_id: int
    change: Literal["messageAdded", "messageDeleted"]
    message_id: str
    thread_id: str
    label_ids: tuple[str, ...]


class MockGmailMailbox:
    """One user's mailbox: the current messages plus the full history of changes."""

    def __init__(self, address: str, first_history_id: int) -> None:
        self.address = address
        self.messages: dict[str, StoredGmailMessage] = {}
        self.history: list[GmailHistoryRecord] = []
        # The mailbox's latest historyId, which users.getProfile returns. Only ever grows.
        self.current_history_id = first_history_id
        # The oldest startHistoryId users.history.list still accepts. Gmail keeps history for a limited time
        # (about a week); asking from before this point is a "history gap" and gets a 404, which tells the
        # client to run a full sync. Starts at the very beginning; fault controls (step 6) can raise it.
        self.oldest_available_history_id = first_history_id

    def _take_next_history_id(self) -> int:
        self.current_history_id += 1
        return self.current_history_id

    def add_message(self, message: DatasetMessage) -> StoredGmailMessage:
        if message.id in self.messages:
            raise MockStateError(f"message {message.id} is already in the mailbox")
        history_id = self._take_next_history_id()
        stored = StoredGmailMessage(
            message_id=message.id,
            thread_id=message.thread_id,
            label_ids=tuple(message.labels),
            internal_date_ms=int(message.sent_at.timestamp() * 1000),
            raw_rfc822=(raw := render_rfc822_bytes(message)),
            history_id=history_id,
            # Gmail's snippet is the start of the body as plain text, whitespace collapsed.
            snippet=" ".join(message.body.split())[:100],
            size_estimate=len(raw),
        )
        self.messages[message.id] = stored
        self.history.append(
            GmailHistoryRecord(history_id, "messageAdded", message.id, message.thread_id, stored.label_ids)
        )
        return stored

    def delete_message(self, message_id: str) -> None:
        """Permanently delete (not trash): the message disappears and a messageDeleted record is added."""
        stored = self.messages.pop(message_id, None)
        if stored is None:
            raise MockStateError(f"message {message_id} is not in the mailbox")
        self.history.append(
            GmailHistoryRecord(
                self._take_next_history_id(), "messageDeleted", message_id, stored.thread_id, stored.label_ids
            )
        )


# --- Calendar ------------------------------------------------------------------------------------------


def render_event_time(time: DatasetEventTime) -> dict[str, str]:
    """A start/end in Calendar API v3 shape: {"date"} for all-day, {"dateTime", "timeZone"} for timed.

    The local wall time gets its zone attached here, so the offset in `dateTime` is whatever that zone
    uses on that date (e.g. -08:00 in winter, -07:00 in summer for Los Angeles).
    """
    if time.date is not None:
        return {"date": time.date.isoformat()}
    assert time.date_time is not None and time.time_zone is not None  # guaranteed by DatasetEventTime
    aware = time.date_time.replace(tzinfo=ZoneInfo(time.time_zone))
    return {"dateTime": aware.isoformat(), "timeZone": time.time_zone}


def shift_event_time(time: DatasetEventTime, step: timedelta) -> DatasetEventTime:
    """Move a start/end by a whole number of days in LOCAL wall time.

    Shifting the local time (then attaching the zone in render_event_time), instead of shifting a UTC
    instant, is what keeps a weekly 09:00 meeting at 09:00 after a daylight-saving change.
    """
    if time.date is not None:
        return time.model_copy(update={"date": time.date + step})
    assert time.date_time is not None
    return time.model_copy(update={"date_time": time.date_time + step})


def instance_id(series_id: str, start: DatasetEventTime) -> str:
    """Google's ID for one occurrence of a series: <series id>_<start in UTC> (or _<date> if all-day)."""
    if start.date is not None:
        return f"{series_id}_{start.date:%Y%m%d}"
    assert start.date_time is not None and start.time_zone is not None
    utc_start = start.date_time.replace(tzinfo=ZoneInfo(start.time_zone)).astimezone(UTC)
    return f"{series_id}_{utc_start:%Y%m%dT%H%M%SZ}"


def build_event_resources(event: DatasetEvent, calendar_owner: str, created_at: datetime) -> list[dict[str, Any]]:
    """The event as Calendar API v3 resources: one for a single event, one per occurrence for a series.

    Decision: the mock stores and serves only expanded occurrences, never the series ("master event")
    itself. The SolNexus calendar contract has the master read with singleEvents=true, which makes Google
    return occurrences too, so the series resource would never be requested.
    """
    occurrences = [(event.start, event.end)]
    if event.recurrence:
        match = SUPPORTED_RECURRENCE.match(event.recurrence)
        assert match is not None  # guaranteed by DatasetEvent validation
        frequency, count = match.group(1), int(match.group(2))
        step = timedelta(days=1 if frequency == "DAILY" else 7)
        occurrences = [
            (shift_event_time(event.start, step * n), shift_event_time(event.end, step * n)) for n in range(count)
        ]

    resources = []
    for start, end in occurrences:
        resource: dict[str, Any] = {
            "kind": "calendar#event",
            "id": instance_id(event.id, start) if event.recurrence else event.id,
            "status": "confirmed",
            "created": format_google_timestamp(created_at),
            "summary": event.summary,
            "description": event.description,
            # Google adds "self": true only when the calendar's owner is that person, never "self": false.
            "organizer": {"email": event.organizer, **({"self": True} if event.organizer == calendar_owner else {})},
            "creator": {"email": event.organizer},
            "attendees": [
                {
                    "email": attendee.email,
                    "responseStatus": attendee.response_status,
                    **({"organizer": True} if attendee.email == event.organizer else {}),
                    **({"self": True} if attendee.email == calendar_owner else {}),
                }
                for attendee in event.attendees
            ],
            "start": render_event_time(start),
            "end": render_event_time(end),
            # One iCalUID per series, shared by every occurrence, as in Google.
            "iCalUID": f"{event.id}@{MOCK_ID_DOMAIN}",
            # Google's own revision number: bumped when the time changes (see reschedule_event).
            "sequence": 0,
        }
        if event.recurrence:
            resource["recurringEventId"] = event.id
            resource["originalStartTime"] = render_event_time(start)
        resources.append(resource)
    return resources


@dataclass(frozen=True)
class StoredCalendarEvent:
    """The latest version of one event, plus the change counter value it was written at."""

    resource: dict[str, Any]
    change_number: int


class MockGoogleCalendar:
    """One calendar: the latest version of every event, and a counter that numbers every change."""

    def __init__(self, calendar_id: str, owner: str, time_zone: str) -> None:
        self.calendar_id = calendar_id
        self.owner = owner
        self.time_zone = time_zone
        self.events: dict[str, StoredCalendarEvent] = {}
        # Incremented on every write. Sync tokens (step 4) will be positions on this counter, so "changes
        # since my token" is simply "events whose change_number is greater than the token's position".
        self.change_counter = 0
        # Sync tokens below this position are expired: Google answers 410 fullSyncRequired and the client must
        # run a full sync again. Starts at 0 (nothing expired); fault controls (step 6) can raise it.
        self.oldest_valid_sync_position = 0

    def _write_version(self, resource: dict[str, Any], at: datetime) -> None:
        """Store a new version: next change number, a new etag and a new `updated` time."""
        self.change_counter += 1
        # Google's etags are opaque quoted strings that change on every write; the counter gives exactly that.
        resource["etag"] = f'"{self.change_counter:016d}"'
        resource["updated"] = format_google_timestamp(at)
        self.events[resource["id"]] = StoredCalendarEvent(resource, self.change_counter)

    def add_event(self, event: DatasetEvent, at: datetime) -> list[str]:
        """Add a single event or a whole series; returns the stored event IDs."""
        resources = build_event_resources(event, self.owner, created_at=at)
        clashes = [r["id"] for r in resources if r["id"] in self.events]
        if clashes:
            raise MockStateError(f"event id(s) already in the calendar: {', '.join(clashes)}")
        for resource in resources:
            self._write_version(resource, at)
        return [r["id"] for r in resources]

    def _latest_resource_copy(self, event_id: str) -> dict[str, Any]:
        stored = self.events.get(event_id)
        if stored is None:
            raise MockStateError(f"event {event_id} is not in the calendar")
        if stored.resource["status"] == "cancelled":
            raise MockStateError(f"event {event_id} is already cancelled")
        # A deep copy: the stored version must never change in place, only be replaced by a new one.
        return copy.deepcopy(stored.resource)

    def reschedule_event(self, event_id: str, start: DatasetEventTime, end: DatasetEventTime, at: datetime) -> None:
        """Move an event (or one occurrence) to a new time: a new version with sequence + 1.

        For an occurrence, originalStartTime is kept: it is how Google says "this used to be the occurrence
        at that time", so clients can match the moved occurrence back to its series slot.
        """
        resource = self._latest_resource_copy(event_id)
        resource["start"] = render_event_time(start)
        resource["end"] = render_event_time(end)
        resource["sequence"] += 1
        self._write_version(resource, at)

    def cancel_event(self, event_id: str, at: datetime) -> None:
        """Cancel (delete) an event or one occurrence: a new version whose status is "cancelled".

        Google keeps cancelled events visible to incremental sync for a while, so clients learn about the
        deletion; the mock keeps them for good. How a cancellation is rendered is the Calendar route's job.
        """
        resource = self._latest_resource_copy(event_id)
        resource["status"] = "cancelled"
        self._write_version(resource, at)


# --- The whole mock ------------------------------------------------------------------------------------


class VirtualClockStartingAt:
    """A clock that starts at a fixed moment and then advances with real elapsed time.

    The mock's "now" starts at the dataset's `seeded_at` instead of the real date. Relative Gmail queries such as
    `newer_than:30d` therefore always match the same seeded messages, whether the tests run today or next year,
    while time still moves forward, so later changes get later `updated` times.
    """

    def __init__(self, start: datetime) -> None:
        self._start = start
        # monotonic(): immune to the host clock being changed while the mock runs.
        self._started_at = time.monotonic()

    def __call__(self) -> datetime:
        return self._start + timedelta(seconds=time.monotonic() - self._started_at)


class MockGoogleState:
    """Everything the mock serves: the mailbox, the calendar, OAuth tokens, injected faults, and progress through
    the scripted changes."""

    def __init__(
        self,
        dataset: MockDataset,
        clock: Callable[[], datetime] | None = None,
        *,
        granted_scopes: tuple[str, ...] = DEFAULT_GRANTED_SCOPES,
        access_token_ttl_seconds: int = 3600,
        default_response_delay_ms: int = 0,
    ) -> None:
        self.dataset = dataset
        # Startup settings that reset() restores (runtime controls may change them in between).
        self._granted_scopes = frozenset(granted_scopes)
        self._access_token_ttl_seconds = access_token_ttl_seconds
        self._default_response_delay_ms = default_response_delay_ms
        # The mock's notion of "now" (see VirtualClockStartingAt). Injectable so tests can freeze time.
        self.clock = clock or VirtualClockStartingAt(dataset.seeded_at)
        # One lock for every read and write. FastAPI runs plain `def` routes on a thread pool, so two
        # requests can touch the state at once. Re-entrant, so a locked method may call another.
        self.lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        """Back to the start: fresh mailbox and calendar from the seed, scripted changes rewound, no issued tokens,
        no revocation and no injected faults."""
        with self.lock:
            self.oauth = MockOAuthServer(self._granted_scopes, self._access_token_ttl_seconds)
            self.faults = FaultPlan(self._default_response_delay_ms)
            mailbox_seed = self.dataset.mailbox
            self.mailbox = MockGmailMailbox(mailbox_seed.address, mailbox_seed.first_history_id)
            # Seed in time order, so history IDs grow with the messages' dates, as they would in Gmail.
            for message in sorted(mailbox_seed.messages, key=lambda m: m.sent_at):
                self.mailbox.add_message(message)

            calendar_seed = self.dataset.calendar
            self.calendar = MockGoogleCalendar(calendar_seed.calendar_id, calendar_seed.owner, calendar_seed.time_zone)
            for event in calendar_seed.events:
                self.calendar.add_event(event, at=self.dataset.seeded_at)

            # Index of the next scripted change apply_next_scripted_change will apply.
            self.next_scripted_change_index = 0

    def apply_scripted_change(self, change: ScriptedChange) -> None:
        """Apply one change from the dataset's scripted list. Raises MockStateError if it cannot apply."""
        with self.lock:
            now = self.clock()
            if isinstance(change, AddMessageChange):
                self.mailbox.add_message(change.message)
            elif isinstance(change, DeleteMessageChange):
                self.mailbox.delete_message(change.message_id)
            elif isinstance(change, AddEventChange):
                self.calendar.add_event(change.event, at=now)
            elif isinstance(change, RescheduleEventChange):
                self.calendar.reschedule_event(change.event_id, change.start, change.end, at=now)
            elif isinstance(change, CancelEventChange):
                self.calendar.cancel_event(change.event_id, at=now)

    def apply_next_scripted_change(self) -> ScriptedChange | None:
        """Apply the next scripted change in order; None when all have been applied (until reset)."""
        with self.lock:
            if self.next_scripted_change_index >= len(self.dataset.scripted_changes):
                return None
            change = self.dataset.scripted_changes[self.next_scripted_change_index]
            self.apply_scripted_change(change)
            self.next_scripted_change_index += 1
            return change


def find_unplayable_dataset_parts(dataset: MockDataset, dataset_file_name: str) -> list[StartupProblem]:
    """Seed a throwaway state and replay every scripted change, reporting each one that cannot apply.

    Schema validation cannot see that, say, change 3 cancels an event that change 1 never created. Doing a
    dry run at startup catches that at boot, with the change's position, instead of mid-test.
    """
    group = f"dataset {dataset_file_name}"
    fix = f"correct this in datasets/{dataset_file_name} (ids must exist at that point in the order)"
    try:
        scratch = MockGoogleState(dataset, clock=lambda: dataset.seeded_at)
    except MockStateError as exc:
        return [StartupProblem(group, f"seed: {exc}", fix)]
    problems = []
    for index, change in enumerate(dataset.scripted_changes):
        try:
            scratch.apply_scripted_change(change)
        except MockStateError as exc:
            problems.append(StartupProblem(group, f"scripted_changes.{index} ({change.kind}): {exc}", fix))
    return problems
