"""Resolve an import field review: staff choose the value for a field the workbook rows disagreed on.

The chosen value may be one of the candidates, a corrected value, or null (leave the field empty). It is
a staff edit of an operational field, so it follows the row-edit rules from the data contract: the clinic
row and its version change in the same transaction as a clinic_field_events audit row (actor, time,
old/new value, reason) and, for status, a staff status event. The review records the decision, and every
batch whose rows were candidates is recounted so its state can reach completed.
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import Connection, text

from app.errors import ApiError
from app.imports.adapters import EMAIL_PATTERN, MAX_FIELD_CHARS, STATUS_LABELS
from app.imports.service import IMPORTED_FIELDS, lock_imports, refresh_batch


def resolve_field_review(conn: Connection, review_id: UUID, value: str | None, reason: str, resolved_by: UUID) -> None:
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
    value = _validated(review.field_name, value)

    clinic = conn.execute(
        text(f"SELECT {review.field_name} AS current FROM app.clinics WHERE clinic_id = :id FOR UPDATE"),
        {"id": review.clinic_id},
    ).one()
    if value != clinic.current:
        # field_name is one of IMPORTED_FIELDS (checked above), never request text, so it is safe in SQL.
        conn.execute(
            text(f"UPDATE app.clinics SET {review.field_name} = :value, version = version + 1 WHERE clinic_id = :id"),
            {"value": value, "id": review.clinic_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO app.clinic_field_events (clinic_id, field_name, old_value, new_value, changed_by, reason)
                VALUES (:clinic_id, :field_name, CAST(:old AS jsonb), CAST(:new AS jsonb), :changed_by, :reason)
                """
            ),
            {
                "clinic_id": review.clinic_id,
                "field_name": review.field_name,
                "old": json.dumps(clinic.current),
                "new": json.dumps(value),
                "changed_by": resolved_by,
                "reason": reason,
            },
        )
        if review.field_name == "status_code":
            conn.execute(
                text(
                    """
                    INSERT INTO app.clinic_status_events (clinic_id, old_status_code, new_status_code, origin, changed_by, reason)
                    VALUES (:clinic_id, :old, :new, 'row_edit', :changed_by, :reason)
                    """
                ),
                {"clinic_id": review.clinic_id, "old": clinic.current, "new": value, "changed_by": resolved_by, "reason": reason},
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


def _validated(field_name: str, value: str | None) -> str | None:
    """Apply the import's own field rules, so a resolved value is as valid as an imported one."""
    value = value.strip() if value is not None else None
    if not value:
        if field_name == "clinic_name":
            raise _invalid(field_name, "required")
        return None
    if len(value) > MAX_FIELD_CHARS:
        raise _invalid(field_name, "too_long")
    if field_name == "status_code" and value not in STATUS_LABELS:
        raise _invalid(field_name, "unknown_status")
    if field_name == "email":
        value = value.lower()
        if not EMAIL_PATTERN.fullmatch(value):
            raise _invalid(field_name, "invalid_email")
    return value


def _invalid(field_name: str, reason: str) -> ApiError:
    return ApiError(422, "validation_error", "Request validation failed", [{"field": "value", "reason": f"{field_name}: {reason}"}])
