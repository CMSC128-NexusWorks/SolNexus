"""Response shapes for /api/v1/imports (contract `import.accepted_response` and `import.result_response`).

Row results carry safe codes and row references. Workbook values appear only where staff must compare
them to decide: proposed fields of a needs_review row, and candidate values of a field review.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

BatchState = Literal["processing", "needs_review", "completed", "failed"]
RowResult = Literal["accepted", "needs_review", "rejected", "skipped"]


class ImportAccepted(BaseModel):
    batch_id: UUID
    state: BatchState
    # True when this exact file was imported before and that earlier batch is returned unchanged.
    replayed: bool


class ImportCounts(BaseModel):
    created_clinics: int
    accepted_rows: int
    needs_review_rows: int
    rejected_rows: int
    skipped_rows: int


class RowCandidate(BaseModel):
    """Another import row (import_row_id, sheet, row) or an existing clinic (clinic_id, clinic_name).

    The row is from this upload, or from an earlier one that still awaited review when this file was
    imported. Once that row is accepted, clinic_id and clinic_name name the clinic it belongs to, so the
    rest of its review group can be linked there.
    """

    import_row_id: UUID | None = None
    sheet: str | None = None
    row: int | None = None
    clinic_id: UUID | None = None
    clinic_name: str | None = None
    # exact_name, similar_name, shared_email, shared_phone or prior_import.
    basis: list[str]


class ImportRowResult(BaseModel):
    import_row_id: UUID
    sheet: str
    row: int
    result: RowResult
    clinic_id: UUID | None
    match_basis: str | None
    # Why a row was rejected (missing_facility, invalid_email, ...). Empty unless rejected.
    reasons: list[str]
    # Accepted-with-caveat codes: unmapped_status, numeric_contact_number, unconfirmed_columns_held.
    warnings: list[str]
    # Rows sharing a review_group are decided together.
    review_group: UUID | None
    candidates: list[RowCandidate]
    # Only for needs_review rows: the values a decision would import.
    proposed_fields: dict[str, str] | None


class FieldReviewCandidate(BaseModel):
    import_row_id: UUID
    sheet: str
    row: int
    value: str | None


class FieldReview(BaseModel):
    review_id: UUID
    clinic_id: UUID | None
    field_name: str
    state: Literal["unresolved", "resolved"]
    resolved_value: str | None
    candidate_rows: list[FieldReviewCandidate]


class ImportResult(BaseModel):
    batch_id: UUID
    state: BatchState
    original_filename: str
    uploaded_at: datetime
    counts: ImportCounts
    rows: list[ImportRowResult]
    field_reviews: list[FieldReview]


class ImportDecisionRequest(BaseModel):
    """Staff decision on needs_review rows of one batch. Rows of one review group are meant to be decided
    together: create_clinic over the whole group is how staff confirm they are the same new clinic."""

    import_row_ids: list[UUID] = Field(min_length=1, max_length=100)
    action: Literal["create_clinic", "link_clinic", "reject"]
    # Required for link_clinic, not allowed otherwise.
    clinic_id: UUID | None = None
    # create_clinic only: the staff-chosen name, required when the rows spell it differently.
    clinic_name: str | None = Field(default=None, max_length=2000)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def check_action_fields(self) -> "ImportDecisionRequest":
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("reason must not be blank")
        if len(set(self.import_row_ids)) != len(self.import_row_ids):
            raise ValueError("import_row_ids must not repeat")
        if (self.action == "link_clinic") != (self.clinic_id is not None):
            raise ValueError("clinic_id is required for link_clinic and not allowed otherwise")
        if self.clinic_name is not None:
            self.clinic_name = self.clinic_name.strip()
            if self.action != "create_clinic" or not self.clinic_name:
                raise ValueError("clinic_name must be a nonblank name and is only used by create_clinic")
        return self


class FieldReviewResolution(BaseModel):
    """The value staff choose for a field the workbook rows disagreed on: a candidate value, a corrected
    value, or null to leave the field empty."""

    value: str | None
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def check_reason(self) -> "FieldReviewResolution":
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("reason must not be blank")
        return self
