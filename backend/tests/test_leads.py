"""SNX-30 integration tests run real migrations, PostgreSQL queries and the actual HTTP routes."""

import re
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import text
from app.db import engine, get_db
from app.main import app

MODELS = Path(__file__).resolve().parents[2] / "dbt" / "models"


def compile_model(name):
    """Inline ephemeral source models for test setup; production uses dbt build unchanged."""
    path = next(MODELS.rglob(name + ".sql"))
    sql = path.read_text(encoding="utf-8")
    sql = re.sub(
        r"\{\{\s*source\('([^']+)',\s*'([^']+)'\)\s*\}\}",
        lambda m: f"{m[1]}.{m[2]}",
        sql,
    )
    return re.sub(
        r"\{\{\s*ref\('([^']+)'\)\s*\}\}",
        lambda m: (
            "silver.interactions"
            if m[1] == "interactions"
            else "(" + compile_model(m[1]) + ")"
        ),
        sql,
    )


def publish(conn):
    for name in ["leads", "interactions"]:
        conn.execute(text(f"DROP TABLE IF EXISTS silver.{name}"))
    conn.exec_driver_sql(
        "CREATE TABLE silver.interactions AS " + compile_model("interactions")
    )
    conn.exec_driver_sql("CREATE TABLE silver.leads AS " + compile_model("leads"))
    conn.execute(
        text(
            """INSERT INTO app.pipeline_runs(pipeline,dag_id,airflow_run_id,status,started_at,finished_at,data_as_of)
            VALUES ('silver_publish','synthetic-publish',gen_random_uuid()::text,'succeeded',clock_timestamp(),clock_timestamp(),clock_timestamp())"""
        )
    )


@pytest.fixture
def db(signed_in):
    # An outer rollback isolates all audited evidence without disabling append-only protection.
    with engine.connect() as conn:
        tx = conn.begin()
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver"))
        publish(conn)

        def request_db():
            with conn.begin_nested():
                yield conn

        app.dependency_overrides[get_db] = request_db
        yield conn
        app.dependency_overrides.pop(get_db, None)
        tx.rollback()


def clinic(
    conn, name="Harbor Test Clinic", status="contacted", days=0, origin="import"
):
    return str(
        conn.execute(
            text(
                """INSERT INTO app.clinics(clinic_name,status_code,next_action_date,origin,email,contact_number)
      VALUES(:name,:status,(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Manila')::date+:days,:origin,'harbor@example.test','09000000001') RETURNING clinic_id"""
            ),
            dict(name=name, status=status, days=days, origin=origin),
        ).scalar_one()
    )


def message(conn, direction="inbound", days=0, participant="lead@example.test"):
    return str(
        conn.execute(
            text("""INSERT INTO bronze.raw_messages
      (source_channel,source_account_id,source_message_id,external_participant_id,direction,source_event_at,raw_payload_bytes,parsed_payload)
      VALUES('gmail','synthetic-mailbox',:key,:participant,:direction,now()+make_interval(days=>:days),:payload,'{"snippet":"Synthetic clinic-name conversation"}'::jsonb)
      RETURNING raw_message_id"""),
            dict(
                key=str(uuid4()),
                participant=participant,
                direction=direction,
                days=days,
                payload=b"{}",
            ),
        ).scalar_one()
    )


def inquiry(conn):
    initial = message(conn, days=-3)
    identity = str(
        conn.execute(
            text(
                """INSERT INTO app.lead_inquiries
      (source_channel,source_account_id,external_participant_id,origin_raw_message_id,email)
      VALUES('gmail','synthetic-mailbox','lead@example.test',:msg,'lead@example.test') RETURNING inquiry_id"""
            ),
            {"msg": initial},
        ).scalar_one()
    )
    question = message(conn, "outbound", -2)
    reply = message(conn, "inbound", -1)
    return identity, initial, question, reply


def confirmation(question, reply, **extra):
    return dict(
        version=1,
        clinic_name="Confirmed Synthetic Clinic",
        question_message_id=question,
        reply_message_id=reply,
        confirm_source_mapping=True,
        reason="Staff reviewed question and subsequent reply",
        **extra,
    )


def test_due_rules_and_readthrough(db, signed_in):
    overdue = clinic(db, days=-2)
    today = clinic(db, "Today Clinic")
    clinic(db, "Future Clinic", days=1)
    clinic(db, "Closed Clinic", status="closed", days=-5)
    nodate = clinic(db, "No Date Clinic")
    db.execute(
        text(
            "UPDATE app.clinics SET version=version+1,next_action_date=NULL WHERE clinic_id=:id"
        ),
        {"id": nodate},
    )
    response = signed_in.get("/api/v1/leads/due")
    assert response.status_code == 200, response.text
    assert [r["lead_id"] for r in response.json()["items"]] == [overdue, today]
    assert all(r["pending_projection"] for r in response.json()["items"])
    publish(db)
    assert not signed_in.get("/api/v1/leads/" + today).json()["pending_projection"]


def test_search_filter_and_keyset(db, signed_in):
    ids = [clinic(db, f"Test Clinic {n}") for n in range(5)]
    first = signed_in.get(
        "/api/v1/leads", params={"q": "TEST", "status": "contacted", "limit": 2}
    ).json()
    assert len(first["items"]) == 2
    second = signed_in.get(
        "/api/v1/leads",
        params={
            "q": "TEST",
            "status": "contacted",
            "limit": 2,
            "cursor": first["next_cursor"],
        },
    ).json()
    assert [r["lead_id"] for r in first["items"] + second["items"]] == ids[:4]
    assert (
        signed_in.get(
            "/api/v1/leads", params={"q": "other", "cursor": first["next_cursor"]}
        ).status_code
        == 422
    )
    assert (
        signed_in.get("/api/v1/leads", params={"q": "%' OR true --"}).json()["items"]
        == []
    )
    assert signed_in.get("/api/v1/leads", params={"limit": 101}).status_code == 422
    assert (
        signed_in.get("/api/v1/leads", params={"cursor": "bad cursor"}).status_code
        == 422
    )


def test_due_pagination_unknown_and_missing(db, signed_in):
    for n in range(3):
        clinic(db, f"Clinic {n}", days=-n)
    identity, *_ = inquiry(db)
    needs = signed_in.get("/api/v1/leads/needs-name").json()["items"]
    assert [r["lead_id"] for r in needs] == [identity]
    first = signed_in.get("/api/v1/leads/due", params={"limit": 1}).json()
    second = signed_in.get(
        "/api/v1/leads/due", params={"limit": 1, "cursor": first["next_cursor"]}
    ).json()
    assert first["items"][0]["lead_id"] != second["items"][0]["lead_id"]
    assert signed_in.get("/api/v1/leads/" + str(uuid4())).status_code == 404


def test_edits_audit_explicit_clear_and_stale_version(db, signed_in, staff):
    identity = clinic(db)
    response = signed_in.patch(
        "/api/v1/clinics/" + identity,
        json={"version": 1, "status_code": None, "email": None},
    )
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["version"] == 2 and row["email"] is None and row["status_code"] is None
    assert (
        db.execute(
            text(
                "SELECT count(*) FROM app.clinic_field_events WHERE clinic_id=:id AND changed_by=:actor"
            ),
            {"id": identity, "actor": staff["user_id"]},
        ).scalar()
        == 2
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM app.clinic_status_events WHERE clinic_id=:id"),
            {"id": identity},
        ).scalar()
        == 1
    )
    assert (
        signed_in.patch(
            "/api/v1/clinics/" + identity,
            json={"version": 1, "email": "stale@example.test"},
        ).status_code
        == 409
    )
    assert signed_in.get("/api/v1/leads/" + identity).json()["email"] is None


def test_validation_and_inquiry_name_guard(db, signed_in):
    identity = clinic(db)
    for body in [
        {"clinic_name": "New Name"},
        {"clinic_name": None},
        {"email": "invalid"},
        {"next_action_date": "tomorrow"},
        {"status_code": "demo_booked"},
        {"raw_payload": "private"},
    ]:
        assert (
            signed_in.patch(
                "/api/v1/clinics/" + identity, json=dict(version=1, **body)
            ).status_code
            == 422
        )
    assert signed_in.get("/api/v1/leads/" + identity).json()["version"] == 1
    inquiry_id, *_ = inquiry(db)
    assert (
        signed_in.patch(
            "/api/v1/inquiries/" + inquiry_id,
            json={"version": 1, "clinic_name": "Guessed"},
        ).status_code
        == 422
    )
    assert (
        signed_in.patch(
            "/api/v1/inquiries/" + inquiry_id,
            json={"version": 1, "next_step": "Ask for name"},
        ).status_code
        == 200
    )


def test_confirmation_evidence_and_audited_transition(db, signed_in):
    identity, initial, question, reply = inquiry(db)
    before = signed_in.get("/api/v1/leads/" + identity + "/history")
    assert before.status_code == 200, before.text
    assert {r["raw_message_id"] for r in before.json()["items"]} == {
        initial,
        question,
        reply,
    }
    path = "/api/v1/inquiries/" + identity + "/confirm-clinic"
    assert signed_in.post(path, json=confirmation(question, initial)).status_code == 422
    assert signed_in.post(path, json=confirmation(reply, question)).status_code == 422
    wrong = message(db, "inbound", participant="other@example.test")
    assert signed_in.post(path, json=confirmation(question, wrong)).status_code == 422
    response = signed_in.post(path, json=confirmation(question, reply))
    assert response.status_code == 200, response.text
    clinic_id = response.json()["clinic_id"]
    assert signed_in.get("/api/v1/leads/needs-name").json()["items"] == []
    history = signed_in.get(f"/api/v1/leads/{clinic_id}/history").json()["items"]
    assert {r["raw_message_id"] for r in history} == {initial, question, reply}
    assert (
        db.execute(
            text("SELECT count(*) FROM app.clinic_field_events WHERE inquiry_id=:id"),
            {"id": identity},
        ).scalar()
        == 1
    )


def test_revocation_hides_published_history_and_last_contact(db, signed_in, staff):
    identity, _, question, reply = inquiry(db)
    response = signed_in.post(
        "/api/v1/inquiries/" + identity + "/confirm-clinic",
        json=confirmation(question, reply),
    )
    assert response.status_code == 200, response.text
    clinic_id = response.json()["clinic_id"]
    publish(db)
    first = signed_in.get(
        f"/api/v1/leads/{clinic_id}/history", params={"limit": 1}
    ).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = signed_in.get(
        f"/api/v1/leads/{clinic_id}/history",
        params={"limit": 1, "cursor": first["next_cursor"]},
    ).json()
    assert second["items"][0]["raw_message_id"] != first["items"][0]["raw_message_id"]
    db.execute(
        text(
            "UPDATE app.clinic_source_identities SET revoked_at=now(),revoked_by=:actor,revoke_reason='test' WHERE clinic_id=:id"
        ),
        {"actor": staff["user_id"], "id": clinic_id},
    )
    assert signed_in.get(f"/api/v1/leads/{clinic_id}/history").json()["items"] == []
    assert signed_in.get("/api/v1/leads/" + clinic_id).json()["last_contact_at"] is None


def test_identity_conflict_does_not_close_inquiry(db, signed_in, staff):
    identity, _, question, reply = inquiry(db)
    other = clinic(db)
    db.execute(
        text(
            """INSERT INTO app.clinic_source_identities(source_channel,source_account_id,external_participant_id,clinic_id,confirmed_by)
      VALUES('gmail','synthetic-mailbox','lead@example.test',:id,:actor)"""
        ),
        {"id": other, "actor": staff["user_id"]},
    )
    response = signed_in.post(
        "/api/v1/inquiries/" + identity + "/confirm-clinic",
        json=confirmation(question, reply),
    )
    assert response.status_code == 409
    assert signed_in.get("/api/v1/leads/" + identity).json()["record_type"] == "inquiry"


def test_metadata_does_not_claim_freshness_after_edit(db, signed_in):
    before = signed_in.get("/api/v1/pipeline/status").json()["published_at"]
    identity = clinic(db)
    signed_in.patch(
        "/api/v1/clinics/" + identity,
        json={"version": 1, "next_step": "Call next week"},
    )
    assert signed_in.get("/api/v1/pipeline/status").json()["published_at"] == before


def test_bounded_replay_resumes_and_preserves_conflicting_evidence(db, signed_in):
    from app.leads.replay import process_batch

    identity, _, question, reply = inquiry(db)
    for _ in range(105):
        message(db)
    conflict = message(db)
    db.execute(
        text(
            "INSERT INTO app.message_resolutions(raw_message_id,resolution_status,review_reason) VALUES(:id,'needs_review','conflicting_evidence')"
        ),
        {"id": conflict},
    )
    response = signed_in.post(
        "/api/v1/inquiries/" + identity + "/confirm-clinic",
        json=confirmation(question, reply),
    )
    # Competing evidence blocks confirmation before any operational state changes.
    assert response.status_code == 409
    db.execute(
        text(
            "UPDATE app.message_resolutions SET review_reason='unconfirmed_source_identity' WHERE raw_message_id=:id"
        ),
        {"id": conflict},
    )
    response = signed_in.post(
        "/api/v1/inquiries/" + identity + "/confirm-clinic",
        json=confirmation(question, reply),
    )
    assert response.status_code == 200, response.text
    assert (
        db.execute(text("SELECT state FROM app.identity_replay_jobs")).scalar()
        == "pending"
    )
    while process_batch(db):
        pass
    count = db.execute(
        text("SELECT count(*) FROM app.message_resolution_events")
    ).scalar()
    assert not process_batch(db)
    assert (
        db.execute(text("SELECT count(*) FROM app.message_resolution_events")).scalar()
        == count
    )
    assert (
        db.execute(
            text(
                "SELECT count(*) FROM app.message_resolutions WHERE resolution_status='linked'"
            )
        ).scalar()
        == 109
    )
