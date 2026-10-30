"""Write a staged workbook into app.clinics and the import ledger (FR-02, NFR-01, NFR-09).

One upload is one transaction under one advisory lock: either every accepted clinic, ledger row and status
baseline commits together, or nothing does and the operator uploads again. The upload limit (10,000
rows) bounds that transaction. The lock serializes imports and staff import decisions, so two uploads of
the same file (a double click, or both staff members) cannot both create clinics.

How each staged row ends up (data contract, "Workbook migration"):

1. Identical file hash as a completed or needs_review batch: return that batch unchanged (replay).
2. Rejected or blank rows: rejected / skipped with safe codes; no clinic write.
3. Same fingerprint as a row accepted before: accepted as prior_import, linked to that clinic, no field
   written. A re-import therefore never overwrites staff edits. Same fingerprint as a row staff rejected:
   rejected again. Fingerprints include the row position, so an edited or moved row is "new".
4. New row with a duplicate candidate (another row in this upload or an existing clinic): needs_review.
   No clinic is created or merged until staff decide (decisions.py).
5. New row without candidates: a new clinic, origin 'import'. Its status, if mapped, is recorded as an
   import baseline observation, not as a dated status transition.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import Connection, text

from app.imports.adapters import StagedRow, stage_workbook
from app.imports.candidates import CandidateKeys, find_candidates, review_groups
from app.imports.workbook import read_workbook

# Held for the transaction by uploads and staff import decisions. "SN28" in ASCII; distinct from the
# silver build lock (BUILD_LOCK_KEY in airflow/include/solnexus_ingest/silver.py).
IMPORT_LOCK_KEY = 0x534E3238

# The clinic fields an adapter can supply, in app.clinics column order.
IMPORTED_FIELDS = (
    "clinic_name", "contact_person", "person_spoken_to", "calling_notes", "contact_number", "email",
    "region", "province", "municipality", "address", "status_code", "next_step",
)


@dataclass(frozen=True)
class ImportOutcome:
    batch_id: UUID
    state: str
    replayed: bool


@dataclass
class PlannedRow:
    staged: StagedRow
    result: str
    import_row_id: UUID = field(default_factory=uuid.uuid4)
    clinic_id: UUID | None = None
    match_basis: str | None = None
    # Extra ledger entries beyond the adapter's issues: duplicate candidates or a reused staff rejection.
    entries: list[dict] = field(default_factory=list)


def stage_upload(data: bytes) -> list[StagedRow]:
    """Parse and stage an upload without touching the database. Raises WorkbookError for a bad file."""
    return stage_workbook(read_workbook(data))


def lock_imports(conn: Connection) -> None:
    conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK_KEY})


def write_import(
    conn: Connection, staged: list[StagedRow], file_sha256: str, filename: str, uploaded_by: UUID
) -> ImportOutcome:
    """Record one upload in the caller's transaction. See the module docstring for the row rules."""
    lock_imports(conn)
    prior = conn.execute(
        text(
            """
            SELECT batch_id, state FROM app.import_batches
            WHERE file_sha256 = :sha AND state IN ('completed', 'needs_review')
            ORDER BY uploaded_at, batch_id
            LIMIT 1
            """
        ),
        {"sha": file_sha256},
    ).first()
    if prior is not None:
        return ImportOutcome(prior.batch_id, prior.state, replayed=True)

    batch_id = conn.execute(
        text(
            """
            INSERT INTO app.import_batches (uploaded_by, file_sha256, original_filename)
            VALUES (:uploaded_by, :sha, :filename)
            RETURNING batch_id
            """
        ),
        {"uploaded_by": uploaded_by, "sha": file_sha256, "filename": filename},
    ).scalar_one()

    planned = [PlannedRow(row, row.result) for row in staged]
    _apply_prior_imports(conn, planned)
    _apply_candidates(conn, planned)

    new_clinics = [row for row in planned if row.result == "valid"]
    for row in new_clinics:
        row.result, row.clinic_id, row.match_basis = "accepted", uuid.uuid4(), "new_clinic"
    insert_clinics(conn, [(row.clinic_id, row.staged.fields) for row in new_clinics], created_by=uploaded_by)
    _insert_rows(conn, batch_id, planned)
    insert_status_baselines(conn, [(row.clinic_id, row.import_row_id, row.staged.fields) for row in new_clinics])

    state = refresh_batch(conn, batch_id)
    return ImportOutcome(batch_id, state, replayed=False)


def _apply_prior_imports(conn: Connection, planned: list[PlannedRow]) -> None:
    """Reuse earlier outcomes for rows whose fingerprint was seen before (retry and re-upload safety)."""
    valid = [row for row in planned if row.result == "valid"]
    if not valid:
        return
    earlier = conn.execute(
        text(
            """
            SELECT row_fingerprint, result, clinic_id FROM app.import_rows
            WHERE row_fingerprint = ANY(:fingerprints)
              AND (result = 'accepted' OR (result = 'rejected' AND decision_id IS NOT NULL))
            """
        ),
        {"fingerprints": [row.staged.fingerprint for row in valid]},
    ).all()
    accepted: dict[str, set[UUID]] = defaultdict(set)
    staff_rejected: set[str] = set()
    for fingerprint, result, clinic_id in earlier:
        if result == "accepted":
            accepted[fingerprint].add(clinic_id)
        else:
            staff_rejected.add(fingerprint)

    for row in valid:
        clinics = accepted.get(row.staged.fingerprint, set())
        if len(clinics) == 1:
            row.result, row.clinic_id, row.match_basis = "accepted", next(iter(clinics)), "prior_import"
        elif len(clinics) > 1:
            # Staff linked the same row to different clinics in different batches: ask again.
            row.result = "needs_review"
            row.entries.append(
                _review_entry(row.import_row_id, [{"clinic_id": str(clinic_id), "basis": ["prior_import"]} for clinic_id in sorted(clinics)])
            )
        elif row.staged.fingerprint in staff_rejected:
            row.result = "rejected"
            row.entries.append({"code": "rejected_by_staff_earlier", "field": None, "severity": "error"})


def _apply_candidates(conn: Connection, planned: list[PlannedRow]) -> None:
    """Hold every new row that may duplicate another new row or an existing clinic for staff review."""
    valid = {row.import_row_id: row for row in planned if row.result == "valid"}
    if not valid:
        return
    clinics = conn.execute(text("SELECT clinic_id, clinic_name, email, contact_number FROM app.clinics")).all()
    found = find_candidates(
        [(row_id, CandidateKeys.from_fields(row.staged.fields)) for row_id, row in valid.items()],
        [(clinic.clinic_id, CandidateKeys.from_fields(clinic._mapping)) for clinic in clinics],
    )
    groups = review_groups(found)
    for row_id, matches in found.items():
        row = valid[row_id]
        row.result = "needs_review"
        ordered = sorted(matches.items(), key=lambda item: (item[0][0], str(item[0][1])))
        candidates = [
            {("import_row_id" if kind == "row" else "clinic_id"): str(ref), "basis": basis}
            for (kind, ref), basis in ordered
        ]
        row.entries.append(_review_entry(groups[row_id], candidates))


def _review_entry(group: UUID, candidates: list[dict]) -> dict:
    return {"code": "possible_duplicate", "field": None, "severity": "review", "group": str(group), "candidates": candidates}


def insert_clinics(conn: Connection, clinics: list[tuple[UUID, dict]], created_by: UUID) -> None:
    """Create clinics from accepted import values. origin 'import'; no field audit event, because the
    import row that supplied each value (import_rows.clinic_id) is the provenance."""
    if not clinics:
        return
    columns = ", ".join(IMPORTED_FIELDS)
    params = ", ".join(f":{name}" for name in IMPORTED_FIELDS)
    conn.execute(
        text(
            f"""
            INSERT INTO app.clinics (clinic_id, {columns}, origin, created_by)
            VALUES (:clinic_id, {params}, 'import', :created_by)
            """
        ),
        [
            {"clinic_id": clinic_id, "created_by": created_by, **{name: fields.get(name) for name in IMPORTED_FIELDS}}
            for clinic_id, fields in clinics
        ],
    )


def insert_status_baselines(conn: Connection, rows: list[tuple[UUID, UUID, dict]]) -> None:
    """Record the workbook status of a newly initialized clinic as an observation tied to its import row.
    It is not a transition: metrics must not read its recorded_at as the date the clinic reached it."""
    params = [
        {"clinic_id": clinic_id, "import_row_id": import_row_id, "status": fields["status_code"]}
        for clinic_id, import_row_id, fields in rows
        if fields.get("status_code")
    ]
    if params:
        conn.execute(
            text(
                """
                INSERT INTO app.clinic_status_events (clinic_id, new_status_code, origin, import_row_id)
                VALUES (:clinic_id, :status, 'import_baseline', :import_row_id)
                """
            ),
            params,
        )


def _ledger_fields(row: PlannedRow) -> dict:
    # Keep values only for rows that reached a clinic or need a staff decision: the minimum needed to
    # reconcile. Rejected and skipped rows keep codes only (retention period still pending approval).
    if row.result not in ("accepted", "needs_review"):
        return {}
    fields = dict(row.staged.fields)
    if row.staged.unmapped:
        fields["unmapped"] = row.staged.unmapped
    return fields


def _insert_rows(conn: Connection, batch_id: UUID, planned: list[PlannedRow]) -> None:
    if not planned:
        return
    conn.execute(
        text(
            """
            INSERT INTO app.import_rows (
                import_row_id, batch_id, sheet_name, row_number, row_fingerprint, adapter_version,
                normalized_fields, validation_errors, result, clinic_id, match_basis
            ) VALUES (
                :import_row_id, :batch_id, :sheet_name, :row_number, :fingerprint, :adapter_version,
                CAST(:normalized_fields AS jsonb), CAST(:validation_errors AS jsonb), :result, :clinic_id,
                :match_basis
            )
            """
        ),
        [
            {
                "import_row_id": row.import_row_id,
                "batch_id": batch_id,
                "sheet_name": row.staged.sheet_name,
                "row_number": row.staged.row_number,
                "fingerprint": row.staged.fingerprint,
                "adapter_version": row.staged.adapter_version,
                "normalized_fields": json.dumps(_ledger_fields(row), ensure_ascii=False),
                "validation_errors": json.dumps([issue.as_json() for issue in row.staged.issues] + row.entries),
                "result": row.result,
                "clinic_id": row.clinic_id,
                "match_basis": row.match_basis,
            }
            for row in planned
        ],
    )


def refresh_batch(conn: Connection, batch_id: UUID) -> str:
    """Recount a batch from its rows and set its state; returns the state.

    needs_review while any row awaits a duplicate decision or any field review over its rows is open,
    which can be true with zero needs_review rows (contract). created_clinics counts clinics this batch's
    rows created, including ones staff created later from its rows, not clinics it was only linked to.
    """
    return conn.execute(
        text(
            """
            WITH counts AS (
                SELECT
                    count(*) FILTER (WHERE result = 'accepted') AS accepted,
                    count(*) FILTER (WHERE result = 'needs_review') AS needs_review,
                    count(*) FILTER (WHERE result = 'rejected') AS rejected,
                    count(*) FILTER (WHERE result = 'skipped') AS skipped,
                    count(DISTINCT clinic_id) FILTER (WHERE match_basis IN ('new_clinic', 'staff_new_clinic')) AS created
                FROM app.import_rows
                WHERE batch_id = :batch_id
            ), open_reviews AS (
                SELECT EXISTS (
                    SELECT 1
                    FROM app.import_field_review_candidates candidate
                    JOIN app.import_field_reviews review USING (review_id)
                    JOIN app.import_rows row ON row.import_row_id = candidate.import_row_id
                    WHERE row.batch_id = :batch_id AND review.state = 'unresolved'
                ) AS any_open
            )
            UPDATE app.import_batches batch SET
                accepted_row_count = counts.accepted,
                needs_review_row_count = counts.needs_review,
                rejected_row_count = counts.rejected,
                skipped_row_count = counts.skipped,
                created_clinic_count = counts.created,
                state = CASE WHEN counts.needs_review > 0 OR open_reviews.any_open THEN 'needs_review' ELSE 'completed' END
            FROM counts, open_reviews
            WHERE batch.batch_id = :batch_id
            RETURNING batch.state
            """
        ),
        {"batch_id": batch_id},
    ).scalar_one()


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_failed_upload(conn: Connection, file_sha256: str, filename: str, uploaded_by: UUID) -> UUID:
    """Leave a visible trace of an upload whose transaction failed after the file was read. It has no rows;
    a failed batch is never treated as a replay, so uploading the file again processes it from scratch."""
    return conn.execute(
        text(
            """
            INSERT INTO app.import_batches (uploaded_by, file_sha256, original_filename, state)
            VALUES (:uploaded_by, :sha, :filename, 'failed')
            RETURNING batch_id
            """
        ),
        {"uploaded_by": uploaded_by, "sha": file_sha256, "filename": filename},
    ).scalar_one()
