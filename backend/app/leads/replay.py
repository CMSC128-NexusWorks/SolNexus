"""Retryable exact-source replay. Run `python -m app.leads.replay` until pending jobs drain."""

from sqlalchemy import text


def process_batch(conn, job_id=None, limit=100):
    """One transaction advances one job by at most 100 messages; changed resolutions get audit events."""
    if not 1 <= limit <= 100:
        raise ValueError("batch size must be 1..100")
    job = (
        conn.execute(
            text("""SELECT * FROM app.identity_replay_jobs WHERE state='pending'
      AND (CAST(:id AS uuid) IS NULL OR job_id=CAST(:id AS uuid)) ORDER BY created_at,job_id
      LIMIT 1 FOR UPDATE SKIP LOCKED"""),
            {"id": str(job_id) if job_id else None},
        )
        .mappings()
        .first()
    )
    if not job:
        return False
    mapping = (
        conn.execute(
            text(
                "SELECT * FROM app.clinic_source_identities WHERE mapping_id=:id FOR SHARE"
            ),
            {"id": job["mapping_id"]},
        )
        .mappings()
        .one()
    )
    if mapping["revoked_at"] is not None:
        conn.execute(
            text(
                "UPDATE app.identity_replay_jobs SET state='superseded',completed_at=now() WHERE job_id=:id"
            ),
            {"id": job["job_id"]},
        )
        return True
    rows = (
        conn.execute(
            text("""SELECT m.raw_message_id FROM bronze.raw_messages m WHERE
      source_channel=:source_channel AND source_account_id=:source_account_id
      AND external_participant_id=:external_participant_id
      AND (CAST(:after AS uuid) IS NULL OR raw_message_id>CAST(:after AS uuid))
      ORDER BY raw_message_id LIMIT :limit"""),
            dict(mapping, after=job["after_id"], limit=limit),
        )
        .mappings()
        .all()
    )
    for row in rows:
        params = dict(
            id=row["raw_message_id"],
            clinic=mapping["clinic_id"],
            actor=job["changed_by"],
            mapping=job["mapping_id"],
        )
        # Insertion first is race-safe against ingestion creating a review row concurrently.
        conn.execute(
            text(
                """INSERT INTO app.message_resolutions(raw_message_id,resolution_status,review_reason)
          VALUES (:id,'needs_review','unconfirmed_source_identity') ON CONFLICT DO NOTHING"""
            ),
            params,
        )
        previous = (
            conn.execute(
                text(
                    "SELECT * FROM app.message_resolutions WHERE raw_message_id=:id FOR UPDATE"
                ),
                params,
            )
            .mappings()
            .one()
        )
        if (
            previous["clinic_id"] == mapping["clinic_id"]
            and previous["resolution_status"] == "linked"
        ):
            continue
        if previous["review_reason"] in (
            "conflicting_evidence",
            "multiple_candidates",
            "multiple_confirmed_mappings",
        ) or previous["clinic_id"] not in (None, mapping["clinic_id"]):
            continue  # Retain competing evidence for a separate staff review.
        conn.execute(
            text(
                """UPDATE app.message_resolutions SET clinic_id=:clinic,resolution_status='linked',
          review_reason=NULL,resolved_by=:actor,resolved_at=now() WHERE raw_message_id=:id"""
            ),
            params,
        )
        conn.execute(
            text(
                """INSERT INTO app.message_resolution_events
          (raw_message_id,mapping_id,old_clinic_id,new_clinic_id,old_status,new_status,reason,changed_by)
          VALUES (:id,:mapping,:old,:clinic,:old_status,'linked','Staff-confirmed exact source replay',:actor)"""
            ),
            dict(
                params,
                old=previous["clinic_id"],
                old_status=previous["resolution_status"],
            ),
        )
    complete = len(rows) < limit
    conn.execute(
        text(
            """UPDATE app.identity_replay_jobs SET after_id=:after,
      state=:state,completed_at=CASE WHEN :done THEN now() ELSE NULL END WHERE job_id=:id"""
        ),
        dict(
            after=rows[-1]["raw_message_id"] if rows else job["after_id"],
            state="complete" if complete else "pending",
            done=complete,
            id=job["job_id"],
        ),
    )
    return True


if __name__ == "__main__":
    from app.db import engine

    # Each batch commits separately. A crash rolls back its cursor and evidence together.
    while True:
        with engine.begin() as connection:
            if not process_batch(connection):
                break
