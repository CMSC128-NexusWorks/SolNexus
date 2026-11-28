"""Regression coverage for PR #22's publication, date, evidence and migration review findings."""

import json
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import text
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from app.errors import install_error_handlers
from test_leads import db, clinic, inquiry, confirmation, publish


def test_pipeline_status_tracks_published_snapshot_not_build_or_failed_run(
    db, signed_in
):
    before = signed_in.get("/api/v1/pipeline/status").json()["published_at"]
    run = str(uuid4())
    db.execute(
        text(
            """INSERT INTO app.pipeline_runs(pipeline,dag_id,airflow_run_id,status,started_at,data_as_of,error_summary)
      VALUES('silver_publish','synthetic-build',:run,'running',clock_timestamp(),clock_timestamp(),'private synthetic diagnostic')"""
        ),
        {"run": run},
    )
    during = signed_in.get("/api/v1/pipeline/status").json()
    assert during["published_at"] == before and during["last_run_status"] == "running"
    db.execute(
        text(
            "UPDATE app.pipeline_runs SET status='failed',finished_at=clock_timestamp() WHERE airflow_run_id=:run"
        ),
        {"run": run},
    )
    failed = signed_in.get("/api/v1/pipeline/status")
    assert (
        failed.json()["published_at"] == before
        and failed.json()["last_run_status"] == "failed"
    )
    assert (
        "private synthetic diagnostic" not in failed.text
        and "dag_id" not in failed.text
    )


def test_no_publication_and_stale_publication_are_honest(db, signed_in):
    db.execute(text("DELETE FROM app.pipeline_runs"))
    payload = signed_in.get("/api/v1/pipeline/status").json()
    assert payload["published_at"] is None and payload["last_run_status"] is None
    assert len(payload["pipelines"]) == 2
    db.execute(
        text(
            """INSERT INTO app.pipeline_runs(pipeline,dag_id,airflow_run_id,status,finished_at,data_as_of)
      VALUES('silver_publish','synthetic-build','stale','succeeded',now(),now()-interval '3 hours')"""
        )
    )
    assert signed_in.get("/api/v1/pipeline/status").json()["is_stale"] is True


def test_optional_business_date_and_cursor_scope(db, signed_in):
    identities = [clinic(db, f"Business-date clinic {n}") for n in range(3)]
    for n, identity in enumerate(identities):
        db.execute(
            text(
                "UPDATE app.clinics SET version=version+1,next_action_date=CAST(:date AS date) WHERE clinic_id=:id"
            ),
            {"date": f"2026-10-{18+n}", "id": identity},
        )
    first = signed_in.get(
        "/api/v1/leads/due", params={"date": "2026-10-19", "limit": 1}
    ).json()
    second = signed_in.get(
        "/api/v1/leads/due",
        params={"date": "2026-10-19", "limit": 1, "cursor": first["next_cursor"]},
    ).json()
    assert [first["items"][0]["lead_id"], second["items"][0]["lead_id"]] == identities[
        :2
    ]
    assert (
        signed_in.get(
            "/api/v1/leads/due",
            params={"date": "2026-10-20", "cursor": first["next_cursor"]},
        ).status_code
        == 422
    )
    assert (
        signed_in.get("/api/v1/leads/due", params={"date": "2026-02-30"}).status_code
        == 422
    )


def test_inquiry_patch_error_matches_contract_fixture(db, signed_in):
    identity, *_ = inquiry(db)
    result = signed_in.patch(
        f"/api/v1/inquiries/{identity}",
        json={"version": 1, "clinic_name": "Guessed Clinic"},
    )
    fixtures = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "docs/contracts/fixtures/phase1-api-examples-v1.json"
        ).read_text()
    )
    expected = fixtures["first_contact_inquiry"]["invalid_initial_name_write"]["error"][
        "code"
    ]
    assert (
        result.status_code == 422
        and result.json()["error"]["code"]
        == expected
        == "confirmation_evidence_required"
    )
    assert (
        "display_clinic_name" not in fixtures["first_contact_inquiry"]["dashboard_row"]
    )
    assert "action_label" not in fixtures["first_contact_inquiry"]["dashboard_row"]


def test_topic_is_an_interaction_suggestion_not_next_step(db, signed_in):
    identity, _, question, reply = inquiry(db)
    result = signed_in.post(
        f"/api/v1/inquiries/{identity}/confirm-clinic",
        json=confirmation(question, reply),
    )
    clinic_id = result.json()["clinic_id"]
    publish(db)
    db.execute(
        text(
            "UPDATE silver.interactions SET topic='Synthetic pricing topic',parser_version='synthetic-v1' WHERE raw_message_id=:id"
        ),
        {"id": reply},
    )
    signed_in.patch(
        f"/api/v1/clinics/{clinic_id}",
        json={"version": 1, "next_step": "Call next week"},
    )
    row = signed_in.get(f"/api/v1/leads/{clinic_id}").json()
    assert (
        row["latest_topic"] == "Synthetic pricing topic"
        and row["next_step"] == "Call next week"
    )


@pytest.mark.parametrize(
    "exception,expected",
    [
        (
            OperationalError(
                "private SQL", {"private": "row"}, Exception("private password")
            ),
            503,
        ),
        (
            ProgrammingError(
                "private SQL", {"private": "row"}, Exception("private password")
            ),
            500,
        ),
        (
            IntegrityError(
                "private SQL", {"private": "row"}, Exception("private password")
            ),
            500,
        ),
    ],
)
def test_database_errors_distinguish_retryable_outages_from_defects(
    exception, expected
):
    probe = FastAPI()
    install_error_handlers(probe)

    @probe.get("/probe")
    def fail():
        raise exception

    with TestClient(probe, raise_server_exceptions=False) as client:
        response = client.get("/probe")
    assert response.status_code == expected and "private" not in response.text


def test_unique_constraint_conflict_is_409_not_an_outage():
    class UniqueConflict(Exception):
        sqlstate = "23505"

    probe = FastAPI()
    install_error_handlers(probe)

    @probe.get("/probe")
    def fail():
        raise IntegrityError(
            "private SQL", {"private": "row"}, UniqueConflict("private diagnostic")
        )

    with TestClient(probe, raise_server_exceptions=False) as client:
        response = client.get("/probe")
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "data_conflict"
    )
    assert "private" not in response.text
