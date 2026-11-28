"""FR-21 transactions: row locks, expected versions, and append-only audit evidence."""

import json
from sqlalchemy import text
from app.errors import ApiError
from .repository import FIELDS, INQUIRY_FIELDS, detail
from .replay import process_batch


def lock_row(conn, kind, identity, version):
    # Table and key are internal constants, never interpolated user input.
    table, key = (
        ("clinics", "clinic_id")
        if kind == "clinic"
        else ("lead_inquiries", "inquiry_id")
    )
    row = (
        conn.execute(
            text(f"SELECT * FROM app.{table} WHERE {key}=:id FOR UPDATE"),
            {"id": identity},
        )
        .mappings()
        .first()
    )
    if not row or (kind == "inquiry" and row["state"] != "open"):
        raise ApiError(404, "not_found", "Lead not found")
    if row["version"] != version:
        raise ApiError(
            409, "version_conflict", "This row changed. Refresh it before retrying."
        )
    return dict(row), table, key


def audit(conn, kind, identity, field, old, new, actor, reason=None, evidence=None):
    """JSON null preserves explicit clears; audit and row update share the request transaction."""
    target = "clinic_id" if kind == "clinic" else "inquiry_id"
    conn.execute(
        text(
            f"""INSERT INTO app.clinic_field_events
      ({target}, field_name, old_value, new_value, changed_by, reason, evidence_message_ids)
      VALUES (:id,:field,CAST(:old AS jsonb),CAST(:new AS jsonb),:actor,:reason,:evidence)"""
        ),
        dict(
            id=identity,
            field=field,
            old=json.dumps(old, default=str),
            new=json.dumps(new, default=str),
            actor=actor,
            reason=reason,
            evidence=evidence,
        ),
    )


def status_event(conn, identity, old, new, actor, origin="row_edit", reason=None):
    if old != new:
        conn.execute(
            text("""INSERT INTO app.clinic_status_events
          (clinic_id,old_status_code,new_status_code,origin,changed_by,reason)
          VALUES (:id,:old,:new,:origin,:actor,:reason)"""),
            dict(
                id=identity, old=old, new=new, origin=origin, actor=actor, reason=reason
            ),
        )


def edit(conn, kind, identity, body, actor):
    """Lock and validate one versioned draft, committing operational state and audit atomically."""
    old, table, key = lock_row(conn, kind, identity, body.version)
    values = body.model_dump(exclude_unset=True, exclude={"version", "reason"})
    allowed = FIELDS + ["clinic_name"] if kind == "clinic" else INQUIRY_FIELDS
    if kind == "inquiry" and "clinic_name" in values:
        raise ApiError(
            422,
            "confirmation_evidence_required",
            "Clinic name requires staff-reviewed reply evidence",
        )
    if any(f not in allowed for f in values):
        raise ApiError(
            422,
            "validation_error",
            "This field is not editable for an inquiry",
            [
                {"field": field, "reason": "Not editable for an inquiry"}
                for field in values
                if field not in allowed
            ],
        )
    if "clinic_name" in values:
        if not values["clinic_name"] or not values["clinic_name"].strip():
            raise ApiError(
                422,
                "validation_error",
                "Clinic name cannot be blank",
                [{"field": "clinic_name", "reason": "Required"}],
            )
        if (
            values["clinic_name"] != old["clinic_name"]
            and not (body.reason or "").strip()
        ):
            raise ApiError(
                422,
                "validation_error",
                "A name correction needs a reason",
                [{"field": "reason", "reason": "Required for name correction"}],
            )
    changes = {f: v for f, v in values.items() if old[f] != v}
    if changes:
        for field, value in changes.items():
            audit(conn, kind, identity, field, old[field], value, actor, body.reason)
        if kind == "clinic" and "status_code" in changes:
            status_event(
                conn,
                identity,
                old["status_code"],
                changes["status_code"],
                actor,
                reason=body.reason,
            )
        conn.execute(
            text(
                f"UPDATE app.{table} SET version=version+1, "
                + ",".join(f"{f}=:{f}" for f in changes)
                + f" WHERE {key}=:id"
            ),
            dict(changes, id=identity),
        )
    return detail(conn, identity)


def confirm(conn, identity, body, actor):
    """Require reviewed exact-source question/reply evidence before creating a durable identity link.

    The request transaction owns the inquiry lock, mapping decision, field/status evidence and
    resumable replay job. Any stale version or competing evidence rolls all of them back.
    """
    inquiry, _, _ = lock_row(conn, "inquiry", identity, body.version)
    name = body.clinic_name.strip()
    if not name or not body.reason.strip() or not inquiry["external_participant_id"]:
        raise ApiError(
            422,
            "invalid_evidence",
            "A complete source identity, name and reason are required",
        )
    # Serialize all confirmations of one exact source key, including two different inquiries.
    source = {
        k: inquiry[k]
        for k in ["source_channel", "source_account_id", "external_participant_id"]
    }
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": json.dumps(source, sort_keys=True)},
    )
    messages = (
        conn.execute(
            text("""SELECT * FROM bronze.raw_messages
      WHERE raw_message_id IN (:question,:reply)"""),
            dict(question=body.question_message_id, reply=body.reply_message_id),
        )
        .mappings()
        .all()
    )
    by_id = {r["raw_message_id"]: r for r in messages}
    question, reply = by_id.get(body.question_message_id), by_id.get(
        body.reply_message_id
    )
    if (
        not question
        or not reply
        or question["direction"] != "outbound"
        or reply["direction"] != "inbound"
        or any(m[k] != source[k] for m in messages for k in source)
        or question["raw_message_id"] == reply["raw_message_id"]
        or reply["raw_message_id"] == inquiry["origin_raw_message_id"]
        or not question["source_event_at"]
        or not reply["source_event_at"]
        or reply["source_event_at"] <= question["source_event_at"]
    ):
        raise ApiError(
            422,
            "invalid_evidence",
            "Select an outbound question and a later inbound reply for this source identity",
        )
    active = conn.execute(
        text("""SELECT clinic_id FROM app.clinic_source_identities WHERE
      source_channel=:source_channel AND source_account_id=:source_account_id
      AND external_participant_id=:external_participant_id AND revoked_at IS NULL"""),
        source,
    ).scalar()
    if active and active != body.clinic_id:
        raise ApiError(
            409,
            "identity_conflict",
            "This source identity already belongs to another clinic",
        )
    # Conflicting or competing evidence remains in review instead of silently changing associations.
    conflicts = conn.execute(
        text(
            """SELECT 1 FROM app.message_resolutions r JOIN bronze.raw_messages m USING(raw_message_id)
      WHERE m.source_channel=:source_channel AND m.source_account_id=:source_account_id
      AND m.external_participant_id=:external_participant_id
      AND (r.review_reason IN ('conflicting_evidence','multiple_candidates','multiple_confirmed_mappings')
           OR (r.clinic_id IS NOT NULL AND r.clinic_id IS DISTINCT FROM :clinic)) LIMIT 1"""
        ),
        dict(source, clinic=body.clinic_id),
    ).first()
    if conflicts:
        raise ApiError(
            409,
            "identity_conflict",
            "Resolve competing message evidence before confirming",
        )
    clinic = body.clinic_id
    if clinic:
        existing = conn.execute(
            text("SELECT clinic_name FROM app.clinics WHERE clinic_id=:id FOR UPDATE"),
            {"id": clinic},
        ).scalar()
        if existing is None:
            raise ApiError(404, "not_found", "Clinic not found")
        if existing != name:
            raise ApiError(
                409,
                "identity_conflict",
                "The selected clinic name differs from the reviewed name",
            )
    else:
        values = {f: inquiry[f] for f in INQUIRY_FIELDS}
        clinic = conn.execute(
            text(
                "INSERT INTO app.clinics (clinic_name,origin,created_by,"
                + ",".join(values)
                + ") VALUES (:name,'inquiry',:actor,"
                + ",".join(":" + f for f in values)
                + ") RETURNING clinic_id"
            ),
            dict(values, name=name, actor=actor),
        ).scalar_one()
        for field, value in dict(values, clinic_name=name).items():
            if value is not None:
                audit(
                    conn,
                    "clinic",
                    clinic,
                    field,
                    None,
                    value,
                    actor,
                    body.reason,
                    [body.question_message_id, body.reply_message_id],
                )
        status_event(
            conn,
            clinic,
            None,
            inquiry["status_code"],
            actor,
            "inquiry_confirmation",
            body.reason,
        )
    if not active:
        conn.execute(
            text(
                """INSERT INTO app.clinic_source_identities
          (source_channel,source_account_id,external_participant_id,clinic_id,confirmed_by,reason)
          VALUES (:source_channel,:source_account_id,:external_participant_id,:clinic,:actor,:reason)"""
            ),
            dict(source, clinic=clinic, actor=actor, reason=body.reason),
        )
    audit(
        conn,
        "inquiry",
        identity,
        "clinic_name",
        None,
        name,
        actor,
        body.reason,
        [body.question_message_id, body.reply_message_id],
    )
    conn.execute(
        text(
            """UPDATE app.lead_inquiries SET version=version+1,state='closed',closed_at=now(),
      confirmed_clinic_id=:clinic,clinic_name_state='confirmed' WHERE inquiry_id=:id"""
        ),
        dict(clinic=clinic, id=identity),
    )
    # Only the reviewed question/reply are linked synchronously. Earlier unreviewed evidence is kept
    # for the ingestion/re-evaluation workflow; no broad name-based or mailbox-based linking occurs.
    for message in messages:
        previous = (
            conn.execute(
                text(
                    "SELECT * FROM app.message_resolutions WHERE raw_message_id=:id FOR UPDATE"
                ),
                {"id": message["raw_message_id"]},
            )
            .mappings()
            .first()
        )
        if (
            previous
            and previous["clinic_id"] == clinic
            and previous["resolution_status"] == "linked"
        ):
            continue
        conn.execute(
            text(
                """INSERT INTO app.message_resolutions(raw_message_id,clinic_id,resolution_status,resolved_by,resolved_at)
          VALUES (:id,:clinic,'linked',:actor,now()) ON CONFLICT(raw_message_id) DO UPDATE
          SET clinic_id=:clinic,resolution_status='linked',review_reason=NULL,resolved_by=:actor,resolved_at=now()"""
            ),
            dict(id=message["raw_message_id"], clinic=clinic, actor=actor),
        )
        conn.execute(
            text("""INSERT INTO app.message_resolution_events
          (raw_message_id,old_clinic_id,new_clinic_id,old_status,new_status,reason,changed_by)
          VALUES (:id,:old,:clinic,:status,'linked',:reason,:actor)"""),
            dict(
                id=message["raw_message_id"],
                old=previous["clinic_id"] if previous else None,
                clinic=clinic,
                status=previous["resolution_status"] if previous else None,
                reason=body.reason,
                actor=actor,
            ),
        )
    mapping_id = conn.execute(
        text("""SELECT mapping_id FROM app.clinic_source_identities
      WHERE source_channel=:source_channel AND source_account_id=:source_account_id
      AND external_participant_id=:external_participant_id AND revoked_at IS NULL"""),
        source,
    ).scalar_one()
    job = conn.execute(
        text("""INSERT INTO app.identity_replay_jobs(mapping_id,changed_by)
      VALUES (:mapping,:actor) RETURNING job_id"""),
        dict(mapping=mapping_id, actor=actor),
    ).scalar_one()
    # Small histories finish immediately; large histories remain durable, bounded worker jobs.
    process_batch(conn, job)
    return dict(detail(conn, clinic), reevaluation_job_id=job)
