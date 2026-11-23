"""Initial clinic resolution for a newly ingested message (docs/contracts/phase1-identity-v1.md).

Only a staff-confirmed mapping for the exact (channel, account, participant) key can link a message.
Clinic emails from the workbook are candidate evidence: they choose the review reason, never a link.
Conflicting-evidence detection is not implemented yet, so no message is sent to review for
'conflicting_evidence' by this baseline; that rule belongs to a later parser/resolution ticket.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from solnexus_ingest.envelope import MessageEnvelope

ReviewReason = Literal[
    "no_match",
    "multiple_candidates",
    "unconfirmed_source_identity",
    "incomplete_source_identity",
    "multiple_confirmed_mappings",
]


@dataclass(frozen=True)
class Resolution:
    status: Literal["linked", "needs_review"]
    clinic_id: UUID | None = None
    mapping_id: UUID | None = None
    review_reason: ReviewReason | None = None


def decide(
    envelope: MessageEnvelope,
    active_mappings: list[tuple[UUID, UUID]],
    candidate_clinic_ids: list[UUID],
) -> Resolution:
    """Resolve one message.

    active_mappings: (mapping_id, clinic_id) of unrevoked staff confirmations for the message's
    exact source key. candidate_clinic_ids: clinics whose stored email equals the participant.
    """
    if envelope.external_participant_id is None:
        return Resolution("needs_review", review_reason="incomplete_source_identity")
    if len(active_mappings) == 1:
        mapping_id, clinic_id = active_mappings[0]
        return Resolution("linked", clinic_id=clinic_id, mapping_id=mapping_id)
    if len(active_mappings) > 1:
        # A partial unique index prevents this today; kept so bad historical data still goes to review.
        return Resolution("needs_review", review_reason="multiple_confirmed_mappings")
    if len(candidate_clinic_ids) == 1:
        return Resolution("needs_review", review_reason="unconfirmed_source_identity")
    if len(candidate_clinic_ids) > 1:
        return Resolution("needs_review", review_reason="multiple_candidates")
    return Resolution("needs_review", review_reason="no_match")


def opens_inquiry(envelope: MessageEnvelope, resolution: Resolution) -> bool:
    """Whether this message is a first contact that should appear as "Clinic name unknown".

    Only an inbound message from a participant who matches no known clinic qualifies. A message with
    a candidate clinic goes to review instead, so staff link it to that clinic rather than seeing a
    duplicate unknown lead. Outbound mail never opens an inquiry: we wrote first, so staff already
    know who they contacted.
    """
    return envelope.direction == "inbound" and resolution.review_reason == "no_match"
