"""Staff decisions on needs_review import rows: possible duplicates the importer will not decide alone.

Data contract rules this implements:

* create_clinic: the rows are one new clinic. Values are merged without regard to sheet or row order:
  one distinct value fills the field, several distinct values leave it unset and open an
  import_field_review naming every row that supplied one. A clinic name the rows disagree on must be
  chosen by staff (clinic_name in the request): the contract forbids creating a partly identified clinic.
* link_clinic: the rows are an existing clinic. Existing values never change. A field staff edited or
  cleared (a clinic_field_events row), or settled in a resolved import review, is authoritative and the
  rows' values for it are dropped. A field with an open import review gets the rows added to that review
  rather than a second review. Otherwise a blank field is filled when the rows agree, and a disagreement
  with the rows or the current value opens a review. The name is never changed: differently written names
  are why the rows needed review.
* reject: the rows are not imported; their values are dropped from the ledger and an identical row in a
  later upload is rejected again (service._apply_prior_imports).

Each decision records the deciding staff member, time and reason in app.import_row_decisions. It runs
under the import advisory lock, so it cannot interleave with an upload or another decision.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import Connection, text

from app.errors import ApiError
from app.imports.service import IMPORTED_FIELDS, insert_clinics, insert_status_baselines, lock_imports, refresh_batch

Action = Literal["create_clinic", "link_clinic", "reject"]


@dataclass(frozen=True)
class Decision:
    import_row_ids: list[UUID]
    action: Action
    reason: str
    clinic_id: UUID | None = None
    clinic_name: str | None = None


def decide(conn: Connection, batch_id: UUID, decision: Decision, decided_by: UUID) -> None:
    lock_imports(conn)
    if conn.execute(text("SELECT 1 FROM app.import_batches WHERE batch_id = :id"), {"id": batch_id}).first() is None:
        raise ApiError(404, "not_found", "Import batch not found")
    rows = conn.execute(
        text(
            """
            SELECT import_row_id, batch_id, result, normalized_fields - 'unmapped' AS fields
            FROM app.import_rows WHERE import_row_id = ANY(:ids)
            ORDER BY sheet_name, row_number
            FOR UPDATE
            """
        ),
        {"ids": decision.import_row_ids},
    ).all()
    if len(rows) != len(decision.import_row_ids) or any(row.batch_id != batch_id for row in rows):
        raise ApiError(422, "rows_not_in_batch", "Every row must belong to this import batch")
    if any(row.result != "needs_review" for row in rows):
        # Typically the other staff member decided first; the client should reload the batch.
        raise ApiError(409, "row_already_decided", "Some rows were already decided; reload the import")

    if decision.action == "create_clinic":
        _create_clinic(conn, batch_id, decision, decided_by, rows)
    elif decision.action == "link_clinic":
        _link_clinic(conn, batch_id, decision, decided_by, rows)
    else:
        decision_id = _record(conn, batch_id, decision, decided_by, clinic_id=None)
        conn.execute(
            text(
                """
                UPDATE app.import_rows SET
                    result = 'rejected',
                    decision_id = :decision_id,
                    normalized_fields = '{}'::jsonb,
                    validation_errors = validation_errors
                        || '[{"code": "rejected_by_staff", "field": null, "severity": "error"}]'::jsonb
                WHERE import_row_id = ANY(:ids)
                """
            ),
            {"decision_id": decision_id, "ids": decision.import_row_ids},
        )
    refresh_batch(conn, batch_id)


def _values_by_field(rows) -> dict[str, dict[str, list[UUID]]]:
    """field -> distinct value -> rows that supplied it."""
    values: dict[str, dict[str, list[UUID]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        for field_name in IMPORTED_FIELDS:
            value = row.fields.get(field_name)
            if value is not None:
                values[field_name][value].append(row.import_row_id)
    return values


def _create_clinic(conn, batch_id, decision: Decision, decided_by, rows) -> None:
    values = _values_by_field(rows)
    names = values.pop("clinic_name", {})
    if decision.clinic_name is not None:
        clinic_name = decision.clinic_name
    elif len(names) == 1:
        clinic_name = next(iter(names))
    else:
        raise ApiError(
            422,
            "clinic_name_conflict",
            "The rows name the clinic differently; choose the clinic name",
            [{"field": "clinic_name", "reason": "rows_disagree"}],
        )

    fields = {"clinic_name": clinic_name}
    conflicts: dict[str, list[UUID]] = {}
    for field_name, by_value in values.items():
        if len(by_value) == 1:
            fields[field_name] = next(iter(by_value))
        else:
            conflicts[field_name] = _supplying_rows(by_value)

    clinic_id = uuid.uuid4()
    insert_clinics(conn, [(clinic_id, fields)], created_by=decided_by)
    _accept_rows(conn, batch_id, decision, decided_by, clinic_id, "staff_new_clinic")
    for field_name, row_ids in conflicts.items():
        _open_field_review(conn, clinic_id, field_name, row_ids)
    if "status_code" in fields:
        insert_status_baselines(conn, [(clinic_id, row_id, fields) for row_id in values["status_code"][fields["status_code"]]])


def _link_clinic(conn, batch_id, decision: Decision, decided_by, rows) -> None:
    clinic = conn.execute(
        text("SELECT * FROM app.clinics WHERE clinic_id = :id FOR UPDATE"), {"id": decision.clinic_id}
    ).first()
    if clinic is None:
        raise ApiError(422, "unknown_clinic", "The selected clinic does not exist")
    # Fields whose value staff already decided: edited or cleared in the dashboard, or chosen in a resolved
    # import review. Staff edits are authoritative, so the rows never fill or reopen these.
    decided = set(
        conn.execute(
            text(
                """
                SELECT field_name FROM app.clinic_field_events WHERE clinic_id = :id
                UNION
                SELECT field_name FROM app.import_field_reviews WHERE clinic_id = :id AND state = 'resolved'
                """
            ),
            {"id": decision.clinic_id},
        ).scalars()
    )
    # Open reviews take the rows as extra candidates, so one field never has two open reviews.
    open_reviews = dict(
        conn.execute(
            text(
                """
                SELECT field_name, review_id FROM app.import_field_reviews
                WHERE clinic_id = :id AND state = 'unresolved'
                ORDER BY created_at, review_id
                """
            ),
            {"id": decision.clinic_id},
        ).all()
    )

    values = _values_by_field(rows)
    values.pop("clinic_name", None)
    fills: dict[str, str] = {}
    conflicts: dict[str, list[UUID]] = {}
    joins: dict[UUID, list[UUID]] = {}
    for field_name, by_value in values.items():
        current = getattr(clinic, field_name)
        if field_name in open_reviews:
            joins[open_reviews[field_name]] = _supplying_rows(by_value)
        elif field_name in decided:
            continue
        elif current is not None:
            if set(by_value) != {current}:
                conflicts[field_name] = _supplying_rows(by_value)
        elif len(by_value) == 1:
            fills[field_name] = next(iter(by_value))
        else:
            conflicts[field_name] = _supplying_rows(by_value)

    _accept_rows(conn, batch_id, decision, decided_by, decision.clinic_id, "staff_link")
    if fills:
        assignments = ", ".join(f"{name} = :{name}" for name in fills)
        conn.execute(
            text(f"UPDATE app.clinics SET {assignments}, version = version + 1 WHERE clinic_id = :clinic_id"),
            {"clinic_id": decision.clinic_id, **fills},
        )
    for field_name, row_ids in conflicts.items():
        _open_field_review(conn, decision.clinic_id, field_name, row_ids)
    for review_id, row_ids in joins.items():
        _add_review_candidates(conn, review_id, row_ids)
    if "status_code" in fills:
        insert_status_baselines(
            conn, [(decision.clinic_id, row_id, fills) for row_id in values["status_code"][fills["status_code"]]]
        )


def _record(conn, batch_id, decision: Decision, decided_by, clinic_id) -> UUID:
    return conn.execute(
        text(
            """
            INSERT INTO app.import_row_decisions (batch_id, action, clinic_id, selected_clinic_name, reason, decided_by)
            VALUES (:batch_id, :action, :clinic_id, :clinic_name, :reason, :decided_by)
            RETURNING decision_id
            """
        ),
        {
            "batch_id": batch_id,
            "action": decision.action,
            "clinic_id": clinic_id,
            "clinic_name": decision.clinic_name,
            "reason": decision.reason,
            "decided_by": decided_by,
        },
    ).scalar_one()


def _accept_rows(conn, batch_id, decision: Decision, decided_by, clinic_id: UUID, match_basis: str) -> None:
    decision_id = _record(conn, batch_id, decision, decided_by, clinic_id)
    conn.execute(
        text(
            """
            UPDATE app.import_rows SET
                result = 'accepted', clinic_id = :clinic_id, match_basis = :match_basis, decision_id = :decision_id
            WHERE import_row_id = ANY(:ids)
            """
        ),
        {"clinic_id": clinic_id, "match_basis": match_basis, "decision_id": decision_id, "ids": decision.import_row_ids},
    )


def _supplying_rows(by_value: dict[str, list[UUID]]) -> list[UUID]:
    """Every row that supplied any value for one field."""
    return [row_id for row_ids in by_value.values() for row_id in row_ids]


def _open_field_review(conn, clinic_id: UUID, field_name: str, row_ids: list[UUID]) -> None:
    """Keep conflicting values for staff, with no sheet winning: the clinic field stays as it is."""
    review_id = conn.execute(
        text(
            """
            INSERT INTO app.import_field_reviews (clinic_id, field_name) VALUES (:clinic_id, :field_name)
            RETURNING review_id
            """
        ),
        {"clinic_id": clinic_id, "field_name": field_name},
    ).scalar_one()
    _add_review_candidates(conn, review_id, row_ids)


def _add_review_candidates(conn, review_id: UUID, row_ids: list[UUID]) -> None:
    """Attach rows to a review. Their batches then stay needs_review until the review is resolved."""
    conn.execute(
        text(
            """
            INSERT INTO app.import_field_review_candidates (review_id, import_row_id) VALUES (:review_id, :row_id)
            ON CONFLICT DO NOTHING
            """
        ),
        [{"review_id": review_id, "row_id": row_id} for row_id in sorted(set(row_ids))],
    )
