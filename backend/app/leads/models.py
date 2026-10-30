"""Strict FR-21 input: absent fields stay unchanged; null explicitly clears a value."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal[
    "contacted", "proposal_sent", "awaiting_demo", "follow_up_needed", "closed"
]


class RowEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=4000)
    version: int = Field(ge=1)
    reason: str | None = None
    clinic_name: str | None = None
    contact_person: str | None = None
    contact_number: str | None = None
    email: str | None = None
    status_code: Status | None = None
    next_action_date: date | None = None
    next_step: str | None = None
    calling_notes: str | None = None
    person_spoken_to: str | None = None
    region: str | None = None
    province: str | None = None
    municipality: str | None = None
    address: str | None = None

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if value is not None:
            import re

            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
                raise ValueError("Enter a valid email address")
        return value


class Confirmation(BaseModel):
    """Two distinct persisted messages are mandatory; initial contact alone cannot confirm."""

    model_config = ConfigDict(extra="forbid", str_max_length=4000)
    version: int = Field(ge=1)
    clinic_name: str = Field(min_length=1, max_length=300)
    question_message_id: UUID
    reply_message_id: UUID
    clinic_id: UUID | None = None
    confirm_source_mapping: Literal[True]
    reason: str = Field(min_length=1)
