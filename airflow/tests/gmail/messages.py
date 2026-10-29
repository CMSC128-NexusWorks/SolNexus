"""Synthetic Gmail API messages for tests. Every address is an invented example.test address."""

from __future__ import annotations

import base64
from email.message import EmailMessage

MAILBOX = "sales@soltech.example.test"
LEAD = "lead@clinic.example.test"


def rfc822(
    *,
    sender: str,
    to: str,
    subject: str = "Question about SolTech EMR",
    body: str = "Hello, we would like a demo.",
    cc: str | None = None,
) -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    if cc:
        message["Cc"] = cc
    message["Subject"] = subject
    message.set_content(body)
    return message.as_bytes()


def api_message(
    message_id: str,
    raw: bytes,
    *,
    labels: tuple[str, ...] = ("INBOX",),
    thread_id: str = "thread-1",
    internal_date_ms: str | None = "1792893600000",  # 2026-10-25T02:00:00Z
) -> dict:
    """The JSON shape users.messages.get(format=raw) returns, minus fields the connector ignores."""
    message = {
        "id": message_id,
        "threadId": thread_id,
        "labelIds": list(labels),
        # Gmail returns base64url; strip padding to prove the decoder restores it.
        "raw": base64.urlsafe_b64encode(raw).decode().rstrip("="),
    }
    if internal_date_ms is not None:
        message["internalDate"] = internal_date_ms
    return message


def inbound(message_id: str = "m-in-1", sender: str = LEAD, **kwargs) -> dict:
    return api_message(message_id, rfc822(sender=sender, to=MAILBOX), **kwargs)


def outbound(message_id: str = "m-out-1", to: str = LEAD, **kwargs) -> dict:
    kwargs.setdefault("labels", ("SENT",))
    return api_message(message_id, rfc822(sender=MAILBOX, to=to, body="Thanks, which clinic is this?"), **kwargs)
