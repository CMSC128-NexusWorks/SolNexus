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
