"""Read one import batch back as the contract's result response."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, text

from app.imports.models import (
    FieldReview,
    FieldReviewCandidate,
    ImportCounts,
    ImportResult,
    ImportRowResult,
    RowCandidate,
)


def load_result(conn: Connection, batch_id: UUID) -> ImportResult | None:
    batch = conn.execute(
        text(
            """
            SELECT batch_id, state, original_filename, uploaded_at, created_clinic_count, accepted_row_count,
                   needs_review_row_count, rejected_row_count, skipped_row_count
            FROM app.import_batches WHERE batch_id = :batch_id
            """
        ),
        {"batch_id": batch_id},
    ).first()
    if batch is None:
        return None

    rows = conn.execute(
        text(
            """
            SELECT import_row_id, sheet_name, row_number, result, clinic_id, match_basis, validation_errors,
                   CASE WHEN result = 'needs_review' THEN normalized_fields - 'unmapped' END AS proposed_fields
            FROM app.import_rows WHERE batch_id = :batch_id
            ORDER BY sheet_name, row_number
            """
        ),
        {"batch_id": batch_id},
    ).all()
    refs = {row.import_row_id: (row.sheet_name, row.row_number) for row in rows}
    candidate_clinic_ids = {
        candidate["clinic_id"]
        for row in rows
        for entry in row.validation_errors
        for candidate in entry.get("candidates", [])
        if "clinic_id" in candidate
    }
    clinic_names = dict(
        conn.execute(
            text("SELECT clinic_id::text, clinic_name FROM app.clinics WHERE clinic_id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": sorted(candidate_clinic_ids)},
        ).all()
    ) if candidate_clinic_ids else {}

    return ImportResult(
        batch_id=batch.batch_id,
        state=batch.state,
        original_filename=batch.original_filename,
        uploaded_at=batch.uploaded_at,
        counts=ImportCounts(
            created_clinics=batch.created_clinic_count,
            accepted_rows=batch.accepted_row_count,
            needs_review_rows=batch.needs_review_row_count,
            rejected_rows=batch.rejected_row_count,
            skipped_rows=batch.skipped_row_count,
        ),
        rows=[_row_result(row, refs, clinic_names) for row in rows],
        field_reviews=_field_reviews(conn, batch_id),
    )


def _row_result(row, refs: dict, clinic_names: dict) -> ImportRowResult:
    entries = row.validation_errors
    review = next((entry for entry in entries if entry["code"] == "possible_duplicate"), None)
    candidates = []
    for candidate in (review or {}).get("candidates", []):
        if "import_row_id" in candidate:
            other = UUID(candidate["import_row_id"])
            sheet, number = refs.get(other, (None, None))
            candidates.append(RowCandidate(import_row_id=other, sheet=sheet, row=number, basis=candidate["basis"]))
        else:
            candidates.append(
                RowCandidate(
                    clinic_id=candidate["clinic_id"],
                    clinic_name=clinic_names.get(candidate["clinic_id"]),
                    basis=candidate["basis"],
                )
            )
    return ImportRowResult(
        import_row_id=row.import_row_id,
        sheet=row.sheet_name,
        row=row.row_number,
        result=row.result,
        clinic_id=row.clinic_id,
        match_basis=row.match_basis,
        reasons=[entry["code"] for entry in entries if entry["severity"] == "error"] if row.result == "rejected" else [],
        warnings=[entry["code"] for entry in entries if entry["severity"] == "warning"],
        review_group=review["group"] if review and row.result == "needs_review" else None,
        candidates=candidates if row.result == "needs_review" else [],
        proposed_fields=row.proposed_fields,
    )


def _field_reviews(conn: Connection, batch_id: UUID) -> list[FieldReview]:
    """Field reviews that involve any row of this batch, with every candidate row's value (from any batch)."""
    records = conn.execute(
        text(
            """
            SELECT review.review_id, review.clinic_id, review.field_name, review.state,
                   review.resolved_value #>> '{}' AS resolved_value,
                   row.import_row_id, row.sheet_name, row.row_number,
                   row.normalized_fields ->> review.field_name AS value
            FROM app.import_field_reviews review
            JOIN app.import_field_review_candidates candidate USING (review_id)
            JOIN app.import_rows row ON row.import_row_id = candidate.import_row_id
            WHERE review.review_id IN (
                SELECT batch_candidate.review_id
                FROM app.import_field_review_candidates batch_candidate
                JOIN app.import_rows batch_row ON batch_row.import_row_id = batch_candidate.import_row_id
                WHERE batch_row.batch_id = :batch_id
            )
            ORDER BY review.created_at, review.review_id, row.sheet_name, row.row_number
            """
        ),
        {"batch_id": batch_id},
    ).all()
    reviews: dict[UUID, FieldReview] = {}
    for record in records:
        review = reviews.setdefault(
            record.review_id,
            FieldReview(
                review_id=record.review_id,
                clinic_id=record.clinic_id,
                field_name=record.field_name,
                state=record.state,
                resolved_value=record.resolved_value,
                candidate_rows=[],
            ),
        )
        review.candidate_rows.append(
            FieldReviewCandidate(
                import_row_id=record.import_row_id, sheet=record.sheet_name, row=record.row_number, value=record.value
            )
        )
    return list(reviews.values())
