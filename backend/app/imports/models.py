"""Response shapes for /api/v1/imports (contract `import.accepted_response` and `import.result_response`).

Row results carry safe codes and row references. Workbook values appear only where staff must compare
them to decide: proposed fields of a needs_review row, and candidate values of a field review.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

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
    """Another row of this upload (import_row_id, sheet, row) or an existing clinic (clinic_id, clinic_name)."""

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
