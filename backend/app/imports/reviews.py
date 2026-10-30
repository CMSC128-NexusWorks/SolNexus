"""Resolve an import field review: staff choose the value for a field the workbook rows disagreed on.

The chosen value may be one of the candidates, a corrected value, or null (leave the field empty). It is
a staff edit of an operational field, so it uses the dashboard row editor's building blocks
(app.leads.writes): the same validation (RowEdit), the same version check (lock_row), the same
clinic_field_events audit row (audit) and, for status, the same row_edit status event (status_event).
It does not call writes.edit, which ends by reading the lead back through silver: the import is the
initial migration and usually runs before silver is first published.

The version precondition is what keeps staff edits authoritative. A dashboard edit may have followed the
review, so the request carries the clinic version the reviewer saw (returned with the review alongside the
current value). If another staff member changed the clinic since, the resolution answers 409
version_conflict instead of silently replacing their edit.

The review records the decision, and every batch whose rows were candidates is recounted so its state can
reach completed.
"""

from __future__ import annotations

import json
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import Connection, text

from app.errors import ApiError
from app.imports.service import IMPORTED_FIELDS, lock_imports, refresh_batch
from app.leads.models import RowEdit
from app.leads.writes import audit, lock_row, status_event


def resolve_field_review(
    conn: Connection, review_id: UUID, value: str | None, reason: str, clinic_version: int, resolved_by: UUID
) -> None:
    lock_imports(conn)
    review = conn.execute(
        text("SELECT review_id, clinic_id, field_name, state FROM app.import_field_reviews WHERE review_id = :id FOR UPDATE"),
        {"id": review_id},
    ).first()
    if review is None:
        raise ApiError(404, "not_found", "Field review not found")
    if review.state != "unresolved":
        raise ApiError(409, "review_already_resolved", "This field review was already resolved; reload the import")
    if review.clinic_id is None or review.field_name not in IMPORTED_FIELDS:
        raise ApiError(409, "review_not_resolvable", "This field review cannot be resolved here")

    value = value.strip() if value is not None else None
    if not value:
        # An empty choice is an explicit clear, stored as null like a dashboard clear.
        value = None
    if value is None and review.field_name == "clinic_name":
        raise ApiError(422, "validation_error", "Clinic name cannot be blank", [{"field": "value", "reason": "Required"}])
    try:
        row_edit = RowEdit.model_validate({"version": clinic_version, "reason": reason, review.field_name: value})
    except ValidationError as error:
        # Same rules as the dashboard (length, email, status vocabulary); never echo the rejected value.
        raise ApiError(
            422,
            "validation_error",
            "Request validation failed",
            [{"field": "value", "message": issue["msg"]} for issue in error.errors()],
        ) from error
    field_name = review.field_name
    # Locks the clinic; 409 version_conflict if anyone changed it after the reviewer loaded the review.
    clinic, _, _ = lock_row(conn, "clinic", review.clinic_id, row_edit.version)
    new_value = getattr(row_edit, field_name)
    if clinic[field_name] != new_value:
        # An unchanged value writes nothing, as a dashboard save would.
        audit(conn, "clinic", review.clinic_id, field_name, clinic[field_name], new_value, resolved_by, reason)
        if field_name == "status_code":
            status_event(conn, review.clinic_id, clinic[field_name], new_value, resolved_by, reason=reason)
        # field_name is one of IMPORTED_FIELDS (checked above), never request text, so it is safe in SQL.
        conn.execute(
            text(f"UPDATE app.clinics SET {field_name} = :value, version = version + 1 WHERE clinic_id = :id"),
            {"value": new_value, "id": review.clinic_id},
        )

    conn.execute(
        text(
            """
            UPDATE app.import_field_reviews SET
                state = 'resolved', resolved_value = CAST(:value AS jsonb), resolved_by = :resolved_by,
                resolved_at = now(), resolution_reason = :reason
            WHERE review_id = :id
            """
        ),
        # JSON null records "staff chose empty", which stays distinct from SQL NULL (unresolved).
        {"value": json.dumps(value), "resolved_by": resolved_by, "reason": reason, "id": review_id},
    )
    batch_ids = conn.execute(
        text(
            """
            SELECT DISTINCT row.batch_id
            FROM app.import_field_review_candidates candidate
            JOIN app.import_rows row USING (import_row_id)
            WHERE candidate.review_id = :id
            """
        ),
        {"id": review_id},
    ).scalars()
    for batch_id in list(batch_ids):
        refresh_batch(conn, batch_id)
