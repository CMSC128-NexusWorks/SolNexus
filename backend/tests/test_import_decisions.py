"""Staff decisions on needs_review import rows, against the real database with synthetic workbooks."""

import pytest
from sqlalchemy import text

from app.db import engine
from tests.workbooks import CONTRACT_SHEETS, JACKS, LJS, ljs, xlsx

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def imported(client, data):
    response = client.post("/api/v1/imports", files={"file": ("leads.xlsx", data, XLSX_TYPE)})
    assert response.status_code == 202, response.text
    return client.get(f"/api/v1/imports/{response.json()['batch_id']}").json()


def refs(result):
    return {(row["sheet"], row["row"]): row for row in result["rows"]}


def decide(client, batch, rows, action, **extra):
    body = {"import_row_ids": [row["import_row_id"] for row in rows], "action": action, "reason": "Checked by phone", **extra}
    return client.post(f"/api/v1/imports/{batch['batch_id']}/decisions", json=body)


def clinic_named(run_sql, name):
    (clinic,) = run_sql("SELECT * FROM app.clinics WHERE clinic_name = :name", name=name)
    return clinic


def harborview_pair(result):
    rows = refs(result)
    return [rows[(LJS, 1)], rows[(JACKS, 2)]]


# create_clinic


def test_confirming_the_cross_sheet_pair_creates_one_clinic_and_holds_the_phone_conflict(signed_in, staff, run_sql):
    batch = imported(signed_in, xlsx(CONTRACT_SHEETS))

    response = decide(signed_in, batch, harborview_pair(batch), "create_clinic")

    assert response.status_code == 200, response.text
    result = response.json()
    # The contract's import.result_response after staff confirmed the Harborview identity.
    assert result["state"] == "needs_review"
    assert result["counts"] == {
        "created_clinics": 3, "accepted_rows": 4, "needs_review_rows": 0, "rejected_rows": 2, "skipped_rows": 0,
    }
    rows = refs(result)
    clinic = clinic_named(run_sql, "Harborview Clinic")
    for ref in [(LJS, 1), (JACKS, 2)]:
        assert (rows[ref]["result"], rows[ref]["match_basis"], rows[ref]["clinic_id"]) == (
            "accepted", "staff_new_clinic", str(clinic.clinic_id),
        )
    # Complementary and equal values fill; the two phones disagree, so neither sheet wins.
    assert clinic.contact_number is None
    assert (clinic.email, clinic.status_code, clinic.next_step) == ("harborview@example.test", "contacted", "Call next week")
    assert (clinic.calling_notes, clinic.person_spoken_to, clinic.contact_person) == (
        "Asked for a follow-up email", "Sam Example", "Sam Example",
    )
    (review,) = result["field_reviews"]
    assert (review["clinic_id"], review["field_name"], review["state"]) == (str(clinic.clinic_id), "contact_number", "unresolved")
    assert {(row["sheet"], row["row"], row["value"]) for row in review["candidate_rows"]} == {
        (LJS, 1, "0917 000 0101"), (JACKS, 2, "0917 000 0199"),
    }
    (decision,) = run_sql("SELECT * FROM app.import_row_decisions")
    assert (decision.action, str(decision.clinic_id), str(decision.decided_by), decision.reason) == (
        "create_clinic", str(clinic.clinic_id), staff["user_id"], "Checked by phone",
    )
    # Only the Jacks row supplied the status, so only it is a baseline observation.
    (baseline,) = run_sql("SELECT * FROM app.clinic_status_events WHERE clinic_id = :id", id=clinic.clinic_id)
    assert str(baseline.import_row_id) == rows[(JACKS, 2)]["import_row_id"]


def test_merge_does_not_depend_on_which_row_is_listed_first(signed_in, run_sql):
    batch = imported(signed_in, xlsx(CONTRACT_SHEETS))
    decide(signed_in, batch, list(reversed(harborview_pair(batch))), "create_clinic")
    reversed_clinic = clinic_named(run_sql, "Harborview Clinic")._mapping
    _reset()

    batch = imported(signed_in, xlsx(CONTRACT_SHEETS))
    decide(signed_in, batch, harborview_pair(batch), "create_clinic")
    clinic = clinic_named(run_sql, "Harborview Clinic")._mapping

    ignored = {"clinic_id", "created_at", "updated_at"}
    assert {k: v for k, v in clinic.items() if k not in ignored} == {k: v for k, v in reversed_clinic.items() if k not in ignored}


def _reset():
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        for table in ("clinic_status_events", "import_field_review_candidates", "import_field_reviews", "import_rows",
                      "import_row_decisions", "import_batches", "clinics"):
            conn.execute(text(f"DELETE FROM app.{table}"))


def test_differently_spelled_names_need_a_staff_chosen_name(signed_in, run_sql):
    batch = imported(signed_in, xlsx({LJS: ljs({"C": "Harborview Clinic"}, {"C": "HARBORVIEW  CLINIC"})}))
    rows = batch["rows"]

    refused = decide(signed_in, batch, rows, "create_clinic")
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "clinic_name_conflict"
    assert run_sql("SELECT count(*) FROM app.clinics")[0][0] == 0

    accepted = decide(signed_in, batch, rows, "create_clinic", clinic_name="  Harborview Clinic ")
    assert accepted.status_code == 200
    assert clinic_named(run_sql, "Harborview Clinic").origin == "import"
    assert run_sql("SELECT selected_clinic_name FROM app.import_row_decisions") == [("Harborview Clinic",)]


def test_staff_can_create_separate_clinics_from_one_review_group(signed_in, run_sql):
    batch = imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One", "D": "0917 000 0101"}, {"C": "Clinic Two", "D": "0917 000 0101"})}))
    first, second = batch["rows"]

    decide(signed_in, batch, [first], "create_clinic")
    result = decide(signed_in, batch, [second], "create_clinic").json()

    assert result["state"] == "completed"
    assert result["counts"]["created_clinics"] == 2
    assert {row.clinic_name for row in run_sql("SELECT clinic_name FROM app.clinics")} == {"Clinic One", "Clinic Two"}


def test_a_group_decided_in_parts_shows_the_clinic_the_first_row_became(signed_in, run_sql):
    batch = imported(signed_in, xlsx(CONTRACT_SHEETS))
    ljs_row, jacks_row = harborview_pair(batch)

    result = decide(signed_in, batch, [ljs_row], "create_clinic").json()

    clinic = clinic_named(run_sql, "Harborview Clinic")
    (candidate,) = refs(result)[(JACKS, 2)]["candidates"]
    assert (candidate["import_row_id"], candidate["clinic_id"], candidate["clinic_name"]) == (
        ljs_row["import_row_id"], str(clinic.clinic_id), "Harborview Clinic",
    )
    # Staff can now link the other row there instead of creating Harborview a second time.
    linked = decide(signed_in, batch, [jacks_row], "link_clinic", clinic_id=str(clinic.clinic_id))
    assert linked.status_code == 200
    assert run_sql("SELECT count(*) FROM app.clinics WHERE clinic_name = 'Harborview Clinic'")[0][0] == 1


def test_an_overlapping_upload_waits_for_rows_an_earlier_batch_still_holds(signed_in, run_sql):
    pair = {LJS: ljs({"C": "Clinic One", "E": "one@example.test"}, {"C": "Clinic One", "E": "one@example.test"})}
    first = imported(signed_in, xlsx(pair))
    # A corrected workbook that drops the second row: alone, row 1 has no candidate in its own upload.
    second = imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One", "E": "one@example.test"})}))

    (row,) = second["rows"]
    assert row["result"] == "needs_review"
    assert run_sql("SELECT count(*) FROM app.clinics")[0][0] == 0
    earlier = {(c["sheet"], c["row"], c["import_row_id"]) for c in row["candidates"]}
    assert earlier == {(LJS, 1, first["rows"][0]["import_row_id"]), (LJS, 2, first["rows"][1]["import_row_id"])}

    decide(signed_in, first, first["rows"], "create_clinic")
    clinic = clinic_named(run_sql, "Clinic One")
    again = signed_in.get(f"/api/v1/imports/{second['batch_id']}").json()
    assert {c["clinic_id"] for c in again["rows"][0]["candidates"]} == {str(clinic.clinic_id)}


# link_clinic


def test_linking_fills_only_blank_untouched_fields_and_never_overwrites(signed_in, staff, run_sql):
    imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One", "D": "0917 000 0101", "E": "old@example.test"})}))
    clinic = clinic_named(run_sql, "Clinic One")
    # Staff cleared the email in the dashboard: an explicit clear must not be refilled by an import.
    run_sql("UPDATE app.clinics SET email = NULL, version = version + 1 WHERE clinic_id = :id", id=clinic.clinic_id)
    run_sql(
        """INSERT INTO app.clinic_field_events (clinic_id, field_name, old_value, new_value, changed_by)
           VALUES (:id, 'email', '"old@example.test"', 'null', :staff)""",
        id=clinic.clinic_id, staff=staff["user_id"],
    )
    batch = imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One Medical Center", "D": "0917 000 0199",
                                                "E": "new@example.test", "G": "Sample City", "H": "Workbook note"})}))
    (row,) = batch["rows"]
    assert (row["result"], row["candidates"][0]["basis"]) == ("needs_review", ["similar_name"])

    result = decide(signed_in, batch, [row], "link_clinic", clinic_id=str(clinic.clinic_id)).json()

    linked = clinic_named(run_sql, "Clinic One")
    assert (linked.contact_number, linked.email) == ("0917 000 0101", None)
    assert (linked.municipality, linked.calling_notes) == ("Sample City", "Workbook note")
    assert linked.version == clinic.version + 2
    assert (result["rows"][0]["result"], result["rows"][0]["match_basis"]) == ("accepted", "staff_link")
    (review,) = result["field_reviews"]
    assert (review["field_name"], [r["value"] for r in review["candidate_rows"]]) == ("contact_number", ["0917 000 0199"])
    assert result["state"] == "needs_review"


def test_linking_adds_rows_to_an_open_review_instead_of_opening_a_second_one(signed_in, run_sql):
    batch = imported(signed_in, xlsx(CONTRACT_SHEETS, title="first"))
    decide(signed_in, batch, harborview_pair(batch), "create_clinic")
    clinic = clinic_named(run_sql, "Harborview Clinic")
    later = imported(signed_in, xlsx({LJS: ljs({"C": "Harborview Clinic", "D": "0917 000 0555"})}, title="second"))

    result = decide(signed_in, later, later["rows"], "link_clinic", clinic_id=str(clinic.clinic_id)).json()

    (review,) = result["field_reviews"]
    assert review["field_name"] == "contact_number"
    assert sorted(r["value"] for r in review["candidate_rows"]) == ["0917 000 0101", "0917 000 0199", "0917 000 0555"]
    assert run_sql("SELECT count(*) FROM app.import_field_reviews")[0][0] == 1
    assert result["state"] == "needs_review"


def test_linking_never_reopens_a_field_staff_edited(signed_in, staff, run_sql):
    imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One", "D": "0917 000 0101"})}))
    clinic = clinic_named(run_sql, "Clinic One")
    run_sql("UPDATE app.clinics SET contact_number = '0917 000 0999', version = version + 1 WHERE clinic_id = :id",
            id=clinic.clinic_id)
    run_sql(
        """INSERT INTO app.clinic_field_events (clinic_id, field_name, old_value, new_value, changed_by)
           VALUES (:id, 'contact_number', '"0917 000 0101"', '"0917 000 0999"', :staff)""",
        id=clinic.clinic_id, staff=staff["user_id"],
    )
    batch = imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One Clinic", "D": "0917 000 0101"})}))

    result = decide(signed_in, batch, batch["rows"], "link_clinic", clinic_id=str(clinic.clinic_id)).json()

    assert result["field_reviews"] == [] and result["state"] == "completed"
    assert clinic_named(run_sql, "Clinic One").contact_number == "0917 000 0999"


def test_linking_to_an_unknown_clinic_is_refused(signed_in, run_sql):
    batch = imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One"}, {"C": "clinic one"})}))

    response = decide(signed_in, batch, batch["rows"][:1], "link_clinic", clinic_id="00000000-0000-4000-8000-000000000000")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_clinic"
    assert run_sql("SELECT count(*) FROM app.import_row_decisions")[0][0] == 0


# reject


def test_rejected_rows_drop_their_values_and_stay_rejected_on_reupload(signed_in, run_sql):
    sheets = {LJS: ljs({"C": "Clinic One", "E": "one@example.test"}, {"C": "Clinic One", "E": "one@example.test"})}
    batch = imported(signed_in, xlsx(sheets, title="first save"))
    first, second = batch["rows"]

    decide(signed_in, batch, [first], "create_clinic")
    result = decide(signed_in, batch, [second], "reject").json()

    assert refs(result)[(LJS, 2)]["reasons"] == ["rejected_by_staff"]
    assert run_sql("SELECT normalized_fields FROM app.import_rows WHERE result = 'rejected'") == [({},)]
    again = imported(signed_in, xlsx(sheets, title="second save"))
    assert [(row["result"], row["reasons"], row["match_basis"]) for row in again["rows"]] == [
        ("accepted", [], "prior_import"), ("rejected", ["rejected_by_staff_earlier"], None),
    ]
    assert run_sql("SELECT count(*) FROM app.clinics")[0][0] == 1


def test_reupload_after_a_decision_reuses_it_without_new_clinics_or_reviews(signed_in, run_sql):
    batch = imported(signed_in, xlsx(CONTRACT_SHEETS, title="first save"))
    decide(signed_in, batch, harborview_pair(batch), "create_clinic")

    again = imported(signed_in, xlsx(CONTRACT_SHEETS, title="second save"))

    assert again["counts"]["created_clinics"] == 0
    assert {row["match_basis"] for row in again["rows"] if row["result"] == "accepted"} == {"prior_import"}
    assert run_sql("SELECT count(*) FROM app.clinics")[0][0] == 3
    assert run_sql("SELECT count(*) FROM app.import_field_reviews")[0][0] == 1
    # The open phone review involves the earlier rows, not the new batch's.
    assert again["field_reviews"] == [] and again["state"] == "completed"


# Errors


def test_a_row_decided_by_the_other_staff_member_first_is_a_conflict(signed_in, run_sql):
    batch = imported(signed_in, xlsx(CONTRACT_SHEETS))
    decide(signed_in, batch, harborview_pair(batch), "create_clinic")

    response = decide(signed_in, batch, harborview_pair(batch)[:1], "reject")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "row_already_decided"


def test_rows_of_another_batch_are_refused(signed_in):
    first = imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One"}, {"C": "clinic one"})}, title="a"))
    second = imported(signed_in, xlsx({LJS: ljs({"C": "Clinic Two"}, {"C": "clinic two"})}, title="b"))

    response = decide(signed_in, second, first["rows"][:1], "reject")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "rows_not_in_batch"


def test_unknown_batch_is_not_found(signed_in):
    batch = {"batch_id": "00000000-0000-4000-8000-000000000000"}

    response = decide(signed_in, batch, [{"import_row_id": "00000000-0000-4000-8000-000000000001"}], "reject")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"action": "link_clinic"},
        {"action": "reject", "clinic_id": "00000000-0000-4000-8000-000000000000"},
        {"action": "reject", "clinic_name": "Clinic One"},
        {"action": "reject", "reason": "   "},
        {"action": "explode"},
    ],
)
def test_invalid_decisions_are_validation_errors(signed_in, body):
    batch = imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One"}, {"C": "clinic one"})}))
    payload = {"import_row_ids": [batch["rows"][0]["import_row_id"]], "reason": "Checked", **body}

    response = signed_in.post(f"/api/v1/imports/{batch['batch_id']}/decisions", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
