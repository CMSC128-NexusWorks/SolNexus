"""Channel-agnostic message envelope: what every connector hands to the bronze writer.

Fields mirror the "Message envelope and replay" section of docs/contracts/phase1-data-api-v1.md, so
Phase 2 connectors (Facebook, Viber) can reuse the same writer by producing the same envelope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

Direction = Literal["inbound", "outbound"]


@dataclass(frozen=True)
class MessageEnvelope:
    source_channel: str
    # The connected mailbox or Page. Source IDs are unique only within one account.
    source_account_id: str
    source_message_id: str
    source_thread_id: str | None
    direction: Direction
    # Original sender/recipient identifiers, kept exactly as the source reported them.
    source_sender_id: str | None
    source_recipient_ids: tuple[str, ...]
    # Clinic-side participant (sender if inbound, recipient if outbound) in the connector's canonical
    # form. None when there is no single such participant; resolution then sends it to review.
    external_participant_id: str | None
    # Provider-reported time. None when the provider gave none; never replaced by ingestion time.
    source_event_at: datetime | None
    # Unmodified source bytes: the evidence of record.
    raw_payload_bytes: bytes
    # Query aid derived from the payload (subject, text). Not evidence; may be re-derived later.
    parsed_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QuarantinedMessage:
    """A source message that could not be turned into an envelope or stored.

    Recorded in bronze.quarantined_messages so the run, and its checkpoint, can move past it.
    """

    source_channel: str
    source_account_id: str
    source_message_id: str
    # "<stage>:<exception class>", e.g. "parse_error:HeaderParseError". Never message content.
    reason: str
    # Source bytes when available, as evidence for fixing the parser.
    payload_bytes: bytes | None = None

    @classmethod
    def from_envelope(cls, envelope: MessageEnvelope, reason: str) -> QuarantinedMessage:
        return cls(
            envelope.source_channel,
            envelope.source_account_id,
            envelope.source_message_id,
            reason,
            envelope.raw_payload_bytes,
        )
