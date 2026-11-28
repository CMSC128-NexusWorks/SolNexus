"""The shape of a mock dataset file (datasets/<name>.json), validated when the mock starts.

A dataset seeds the fake Google with one mailbox and one calendar, and lists scripted changes (new mail,
deletions, reschedules, cancellations) that later steps replay to exercise incremental sync. Everything
in it is synthetic: `example.test` addresses and invented names only.

Validation uses pydantic models with `extra="forbid"`, so a typo in a field name is an error rather than
a silently ignored key. All problems are collected and reported together, the same way as settings.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from mock_settings import StartupProblem

# The only recurrence rules the mock expands: a daily or weekly series with a fixed number of occurrences.
# Real Google accepts full RFC 5545 rules; the master never sees rules at all, because it reads events
# expanded (singleEvents=true), so the mock needs just enough to produce realistic instances.
SUPPORTED_RECURRENCE = re.compile(r"^RRULE:FREQ=(DAILY|WEEKLY);COUNT=([1-9][0-9]?)$")


class StrictModel(BaseModel):
    """Base for dataset models: unknown keys are errors, so typos in a dataset fail at startup."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetMessage(StrictModel):
    """One email as it should appear in the fake mailbox; rendered to RFC 822 bytes when loaded."""

    id: str
    thread_id: str
    # Gmail label IDs, e.g. INBOX, SENT, DRAFT, SPAM. The master skips DRAFT, SPAM, TRASH and CHAT.
    labels: list[str]
    # Must carry a UTC offset, because a time without one is ambiguous; Gmail's internalDate comes from it.
    sent_at: dt.datetime
    sender: str
    to: list[str]
    cc: list[str] = []
    subject: str
    body: str
    # Message-ID of the message this one answers, so replies thread like real mail.
    in_reply_to: str | None = None

    @field_validator("sent_at")
    @classmethod
    def sent_at_must_have_an_offset(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            raise ValueError("needs a UTC offset, e.g. 2026-11-18T09:15:00+08:00")
        return value


class DatasetEventTime(StrictModel):
    """An event start or end: either an all-day `date`, or a local `date_time` plus an IANA `time_zone`.

    Local wall time plus zone (not a UTC instant) is how people and Calendly book meetings, and it is what
    makes daylight-saving shifts come out right when a weekly series is expanded.
    """

    # Types are written as dt.date / dt.datetime on purpose: a field named `date` would otherwise hide the
    # `date` type inside this class, and pydantic could no longer evaluate the annotation `date | None`.
    date: dt.date | None = None
    date_time: dt.datetime | None = None
    time_zone: str | None = None

    @model_validator(mode="after")
    def exactly_one_kind_of_time(self) -> DatasetEventTime:
        if (self.date is None) == (self.date_time is None):
            raise ValueError("set either `date` (all-day) or `date_time` + `time_zone`, not both or neither")
        if self.date_time is not None:
            if self.date_time.tzinfo is not None:
                raise ValueError("`date_time` is local wall time; put the zone in `time_zone`, not an offset")
            if not self.time_zone:
                raise ValueError("`date_time` needs a `time_zone`, e.g. Asia/Manila")
            try:
                ZoneInfo(self.time_zone)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(f"unknown time zone {self.time_zone!r}") from exc
        return self


class DatasetAttendee(StrictModel):
    email: str
    response_status: Literal["needsAction", "accepted", "declined", "tentative"] = "needsAction"


class DatasetEvent(StrictModel):
    """One calendar event, or a recurring series when `recurrence` is set."""

    id: str
    summary: str
    description: str = ""
    organizer: str
    attendees: list[DatasetAttendee] = []
    start: DatasetEventTime
    end: DatasetEventTime
    recurrence: str | None = None

    @field_validator("recurrence")
    @classmethod
    def recurrence_must_be_supported(cls, value: str | None) -> str | None:
        if value is not None and not SUPPORTED_RECURRENCE.match(value):
            raise ValueError("only RRULE:FREQ=DAILY;COUNT=n or RRULE:FREQ=WEEKLY;COUNT=n (n < 100) is supported")
        return value

    @model_validator(mode="after")
    def start_and_end_are_the_same_kind(self) -> DatasetEvent:
        if (self.start.date is None) != (self.end.date is None):
            raise ValueError("start and end must both be all-day or both be timed")
        return self


class DatasetMailbox(StrictModel):
    address: str
    # Gmail history IDs only ever grow; seeding starts here so IDs look like real ones, not 1, 2, 3.
    first_history_id: int = Field(ge=1)
    messages: list[DatasetMessage]


class DatasetCalendar(StrictModel):
    # For a user's primary calendar, Google uses the account address as the calendar ID.
    calendar_id: str
    owner: str
    time_zone: str
    events: list[DatasetEvent]


class AddMessageChange(StrictModel):
    kind: Literal["add_message"]
    message: DatasetMessage


class DeleteMessageChange(StrictModel):
    kind: Literal["delete_message"]
    message_id: str


class AddEventChange(StrictModel):
    kind: Literal["add_event"]
    event: DatasetEvent


class RescheduleEventChange(StrictModel):
    kind: Literal["reschedule_event"]
    # A single event's ID, or one occurrence of a series (its instance ID, e.g. evt-x_20261209T020000Z).
    event_id: str
    start: DatasetEventTime
    end: DatasetEventTime


class CancelEventChange(StrictModel):
    kind: Literal["cancel_event"]
    event_id: str


# `kind` picks the model, so each scripted change is validated against exactly the fields it needs.
ScriptedChange = Annotated[
    AddMessageChange | DeleteMessageChange | AddEventChange | RescheduleEventChange | CancelEventChange,
    Field(discriminator="kind"),
]


class MockDataset(StrictModel):
    """A whole dataset file."""

    description: str
    # The clock time given to every seeded event version (created/updated), so seeding is deterministic.
    seeded_at: dt.datetime
    mailbox: DatasetMailbox
    calendar: DatasetCalendar
    scripted_changes: list[ScriptedChange] = []

    @model_validator(mode="after")
    def ids_are_unique(self) -> MockDataset:
        message_ids = [m.id for m in self.mailbox.messages]
        event_ids = [e.id for e in self.calendar.events]
        for kind, ids in (("message", message_ids), ("event", event_ids)):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            if duplicates:
                raise ValueError(f"duplicate {kind} id(s): {', '.join(duplicates)}")
        return self


def read_dataset_or_problems(path: Path) -> tuple[MockDataset | None, list[StartupProblem]]:
    """Parse and validate one dataset file. Returns (dataset, []) or (None, every problem found)."""
    group = f"dataset {path.name}"
    fix = f"correct this in datasets/{path.name}"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [StartupProblem(group, f"cannot be read as JSON ({type(exc).__name__})", fix)]
    try:
        return MockDataset.model_validate(raw), []
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"]) or "(top level)"
            # ascii(): dataset text may contain non-ASCII names; the startup report must stay ASCII-only.
            problems.append(StartupProblem(group, ascii(f"{location}: {error['msg']}")[1:-1], fix))
        return None, problems
