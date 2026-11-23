"""Turn a Gmail API message (format=raw) into a MessageEnvelope.

Why format=raw: the RFC 822 bytes of a Gmail message never change, while the API's JSON wrapper does
(labels, historyId). Storing the RFC 822 bytes as raw_payload_bytes means a replay with different
bytes is a real discrepancy rather than label noise.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from email import policy
from email.headerregistry import Address
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Any

from solnexus_ingest.envelope import MessageEnvelope

SOURCE_CHANNEL = "gmail"
# Bump when parsed_payload's shape or extraction rules change, so stored rows can be told apart.
PARSER_VERSION = "gmail-raw-v1"

# Labels whose messages are not part of a conversation with a lead. Drafts were never sent; spam and
# trash are not conversations staff work from; chats are not email.
SKIPPED_LABELS = frozenset({"DRAFT", "SPAM", "TRASH", "CHAT"})


def should_ingest(label_ids: list[str] | None) -> bool:
    """Whether a message with these Gmail labels belongs in bronze."""
    return not SKIPPED_LABELS.intersection(label_ids or ())


def canonical_address(addr_spec: str) -> str:
    """Canonical form used for external_participant_id.

    Email addresses are compared case-insensitively in practice, so "Lead@Example.test" and
    "lead@example.test" must be one source identity; otherwise a staff-confirmed mapping would miss
    messages that differ only in case. The original spelling stays in source_sender_id/recipient_ids.
    """
    return addr_spec.strip().lower()


def decode_raw(raw: str) -> bytes:
    """Decode Gmail's base64url "raw" field. Gmail may omit the "=" padding."""
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def parse_gmail_message(api_message: dict[str, Any], account_email: str) -> MessageEnvelope:
    """Build the envelope for one message fetched with users.messages.get(format=raw).

    account_email is the connected mailbox's address (users.getProfile), used both as
    source_account_id and to tell our side of the conversation from the clinic's side.
    """
    raw_bytes = decode_raw(api_message["raw"])
    message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    label_ids = list(api_message.get("labelIds") or [])
    account = canonical_address(account_email)

    senders = _addresses(message, "From")
    recipients = _addresses(message, "To", "Cc", "Bcc")
    sender = senders[0].addr_spec if len(senders) == 1 else None

    # Gmail labels the mailbox owner's own sent mail SENT. The From check also covers mail sent from
    # another client that Gmail has not labelled, as long as it uses the connected address.
    outbound = "SENT" in label_ids or (sender is not None and canonical_address(sender) == account)

    if outbound:
        # Our message: the clinic is whoever we wrote to, if that is exactly one other address.
        participants = {canonical_address(a.addr_spec) for a in recipients} - {account}
    else:
        # Their message: the clinic is the single sender.
        participants = {canonical_address(sender)} if sender else set()
    external_participant_id = participants.pop() if len(participants) == 1 else None

    return MessageEnvelope(
        source_channel=SOURCE_CHANNEL,
        source_account_id=account,
        source_message_id=api_message["id"],
        source_thread_id=api_message.get("threadId"),
        direction="outbound" if outbound else "inbound",
        source_sender_id=sender,
        source_recipient_ids=tuple(a.addr_spec for a in recipients),
        external_participant_id=external_participant_id,
        source_event_at=_internal_date(api_message.get("internalDate")),
        raw_payload_bytes=raw_bytes,
        parsed_payload={
            "parser_version": PARSER_VERSION,
            "subject": _header_text(message, "Subject"),
            "text_plain": _plain_text(message),
            "label_ids": label_ids,
        },
    )


def _addresses(message: EmailMessage, *header_names: str) -> list[Address]:
    """All parseable addresses in the given headers. Group syntax and malformed entries are dropped."""
    found: list[Address] = []
    for name in header_names:
        for header in message.get_all(name, []):
            found.extend(a for a in getattr(header, "addresses", ()) if a.addr_spec and "@" in a.addr_spec)
    return found


def _internal_date(value: str | None) -> datetime | None:
    """Gmail's internalDate (epoch milliseconds) as a UTC datetime, or None if absent or invalid.

    internalDate is when Gmail received the message, which is more reliable than the sender-controlled
    Date header; the SNX-21 spike used the same field.
    """
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc) if value else None
    except (TypeError, ValueError, OverflowError):
        return None


def _header_text(message: EmailMessage, name: str) -> str | None:
    value = message.get(name)
    return str(value) if value is not None else None


def _plain_text(message: EmailMessage) -> str | None:
    """The text/plain body, if any. Undecodable bodies yield None instead of failing the whole page."""
    body = message.get_body(preferencelist=("plain",))
    if body is None:
        return None
    try:
        return body.get_content()
    except (LookupError, UnicodeError, ValueError):
        return None
