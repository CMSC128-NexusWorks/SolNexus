"""Workbook upload and result endpoints against the real parser and database, with synthetic workbooks."""

import threading

from sqlalchemy import text

from app.db import engine
from app.imports.service import file_hash, stage_upload, write_import
from tests.workbooks import CONTRACT_SHEETS, JACKS, LJS, jacks, ljs, xlsx

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def upload(client, data, filename="leads.xlsx"):
    return client.post("/api/v1/imports", files={"file": (filename, data, XLSX_TYPE)})


def imported(client, data, filename="leads.xlsx"):
    response = upload(client, data, filename)
    assert response.status_code == 202, response.text
    result = client.get(f"/api/v1/imports/{response.json()['batch_id']}")
    assert result.status_code == 200
    return response.json(), result.json()


def rows_by_ref(result):
    return {(row["sheet"], row["row"]): row for row in result["rows"]}


def clinics(run_sql):
    return {row.clinic_name: row for row in run_sql("SELECT * FROM app.clinics ORDER BY clinic_name")}


# Contract workbook


def test_contract_workbook_creates_clinics_and_holds_the_cross_sheet_pair_for_review(signed_in, run_sql):
    accepted, result = imported(signed_in, xlsx(CONTRACT_SHEETS))

    assert accepted["replayed"] is False
    assert result["state"] == "needs_review"
    assert result["counts"] == {
        "created_clinics": 2, "accepted_rows": 2, "needs_review_rows": 2, "rejected_rows": 2, "skipped_rows": 0,
    }
    rows = rows_by_ref(result)
    assert {ref: row["result"] for ref, row in rows.items()} == {
        (JACKS, 2): "needs_review", (JACKS, 3): "rejected", (JACKS, 4): "accepted",
        (LJS, 1): "needs_review", (LJS, 2): "rejected", (LJS, 3): "accepted",
    }
    # Harborview appears on both sheets: neither is created or merged until staff decide.
    assert rows[(LJS, 1)]["review_group"] == rows[(JACKS, 2)]["review_group"] is not None
    assert rows[(LJS, 1)]["candidates"] == [
        {"import_row_id": rows[(JACKS, 2)]["import_row_id"], "sheet": JACKS, "row": 2,
         "clinic_id": None, "clinic_name": None, "basis": ["exact_name", "shared_email"]}
    ]
    assert rows[(JACKS, 3)]["reasons"] == rows[(LJS, 2)]["reasons"] == ["missing_facility"]
    assert set(clinics(run_sql)) == {"Pinecrest Clinic", "Riverside Clinic"}


def test_ljs_row_1_imports_as_a_clinic_with_notes_and_person_spoken_to_in_their_own_fields(signed_in, run_sql):
    _, result = imported(signed_in, xlsx({LJS: CONTRACT_SHEETS[LJS]}))

    row = rows_by_ref(result)[(LJS, 1)]
    assert (row["result"], row["match_basis"]) == ("accepted", "new_clinic")
    clinic = clinics(run_sql)["Harborview Clinic"]
    assert str(clinic.clinic_id) == row["clinic_id"]
    assert clinic.origin == "import"
    assert clinic.calling_notes == "Asked for a follow-up email"
    assert clinic.person_spoken_to == clinic.contact_person == "Sam Example"
    assert (clinic.region, clinic.province, clinic.municipality, clinic.address) == (
        "Region Sample", "Province Sample", "Sample City", "Sample Street",
    )
    assert clinic.contact_number == "0917 000 0101"


def test_jacks_status_becomes_an_import_baseline_not_a_transition(signed_in, staff, run_sql):
    _, result = imported(signed_in, xlsx({JACKS: jacks({"C": "Clinic One", "H": "Proposal sent", "J": "held"})}))

    row = rows_by_ref(result)[(JACKS, 2)]
    clinic = clinics(run_sql)["Clinic One"]
    assert clinic.status_code == "proposal_sent"
    assert clinic.created_by is not None and str(clinic.created_by) == staff["user_id"]
    (event,) = run_sql("SELECT * FROM app.clinic_status_events WHERE clinic_id = :id", id=clinic.clinic_id)
    assert (event.origin, event.old_status_code, event.new_status_code) == ("import_baseline", None, "proposal_sent")
    assert str(event.import_row_id) == row["import_row_id"]
    assert event.changed_by is None
    # J is held as restricted evidence, not copied into a clinic field.
    assert row["warnings"] == ["unconfirmed_columns_held"]
    assert clinic.point_person is None and clinic.contact_person is None


def test_unmapped_status_leaves_the_clinic_status_null_and_warns(signed_in, run_sql):
    _, result = imported(signed_in, xlsx({JACKS: jacks({"C": "Clinic One", "H": "Interested"})}))

    assert rows_by_ref(result)[(JACKS, 2)]["warnings"] == ["unmapped_status"]
    assert clinics(run_sql)["Clinic One"].status_code is None
    assert run_sql("SELECT count(*) FROM app.clinic_status_events")[0][0] == 0


def test_sheet_order_does_not_change_the_result(signed_in, run_sql):
    _, first = imported(signed_in, xlsx(CONTRACT_SHEETS))
    first_rows = {ref: (row["result"], row["reasons"]) for ref, row in rows_by_ref(first).items()}
    reset_import_tables()

    _, second = imported(signed_in, xlsx({LJS: CONTRACT_SHEETS[LJS], JACKS: CONTRACT_SHEETS[JACKS]}))

    assert {ref: (row["result"], row["reasons"]) for ref, row in rows_by_ref(second).items()} == first_rows
    assert second["counts"] == first["counts"]


def reset_import_tables():
    """Forget a previous import within one test, as the autouse cleanup in conftest does between tests."""
    tables = ("clinic_status_events", "import_rows", "import_batches", "clinics")
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        for table in tables:
            conn.execute(text(f"DELETE FROM app.{table}"))


# Re-imports


def test_reuploading_the_same_file_returns_the_first_batch_unchanged(signed_in, run_sql):
    data = xlsx(CONTRACT_SHEETS)
    first, _ = imported(signed_in, data)

    second = upload(signed_in, data)

    assert second.status_code == 202
    assert second.json() == {"batch_id": first["batch_id"], "state": first["state"], "replayed": True}
    assert run_sql("SELECT count(*) FROM app.import_batches")[0][0] == 1
    assert len(clinics(run_sql)) == 2


def test_resaved_workbook_with_the_same_rows_creates_no_duplicates(signed_in, run_sql):
    sheets = {LJS: ljs({"C": "Clinic One"}, {"C": "Clinic Two", "D": "0917 000 0202"})}
    imported(signed_in, xlsx(sheets, title="first save"))
    before = clinics(run_sql)

    accepted, result = imported(signed_in, xlsx(sheets, title="second save"))

    assert accepted["replayed"] is False
    assert result["counts"]["created_clinics"] == 0
    assert [(row["result"], row["match_basis"]) for row in result["rows"]] == [("accepted", "prior_import")] * 2
    assert [row["clinic_id"] for row in result["rows"]] == [str(before[name].clinic_id) for name in ("Clinic One", "Clinic Two")]
    assert clinics(run_sql).keys() == before.keys()


def test_reimport_never_overwrites_a_staff_edit(signed_in, run_sql):
    sheets = {LJS: ljs({"C": "Clinic One", "D": "0917 000 0101", "H": "Workbook note"})}
    imported(signed_in, xlsx(sheets, title="first save"))
    run_sql(
        "UPDATE app.clinics SET contact_number = '0917 999 9999', calling_notes = NULL, version = version + 1"
    )

    imported(signed_in, xlsx(sheets, title="second save"))

    clinic = clinics(run_sql)["Clinic One"]
    assert (clinic.contact_number, clinic.calling_notes, clinic.version) == ("0917 999 9999", None, 2)


def test_an_edited_row_matching_an_existing_clinic_waits_for_review_instead_of_duplicating(signed_in, run_sql):
    imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One", "D": "0917 000 0101"})}))
    existing = clinics(run_sql)["Clinic One"]

    _, result = imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One", "D": "0917 000 0199"})}))

    (row,) = result["rows"]
    assert row["result"] == "needs_review"
    assert row["candidates"] == [
        {"import_row_id": None, "sheet": None, "row": None, "clinic_id": str(existing.clinic_id),
         "clinic_name": "Clinic One", "basis": ["exact_name"]}
    ]
    assert row["proposed_fields"] == {"clinic_name": "Clinic One", "contact_number": "0917 000 0199"}
    assert len(clinics(run_sql)) == 1
    assert existing.contact_number == clinics(run_sql)["Clinic One"].contact_number == "0917 000 0101"


def test_missing_rows_in_a_later_workbook_never_delete_clinics(signed_in, run_sql):
    imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One"}, {"C": "Clinic Two"})}))

    imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One"})}))

    assert set(clinics(run_sql)) == {"Clinic One", "Clinic Two"}


def test_concurrent_uploads_of_one_file_import_it_once(staff, run_sql):
    # Two staff members (or a double click) uploading together: the advisory lock serializes them and the
    # second sees the first's batch as a replay.
    data = xlsx({LJS: ljs({"C": "Clinic One"}, {"C": "Clinic Two"})})
    staged, sha, outcomes = stage_upload(data), file_hash(data), []
    barrier = threading.Barrier(2)

    def run():
        barrier.wait()
        with engine.begin() as conn:
            outcomes.append(write_import(conn, staged, sha, "leads.xlsx", staff["user_id"]))

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcome.replayed for outcome in outcomes) == [False, True]
    assert len({outcome.batch_id for outcome in outcomes}) == 1
    assert len(clinics(run_sql)) == 2


# Validation and errors


def test_ledger_keeps_codes_but_no_values_for_rejected_rows(signed_in, run_sql):
    _, result = imported(signed_in, xlsx({LJS: ljs({"C": "", "E": "private@example.test", "D": "0917 555 0000"})}))

    (row,) = run_sql("SELECT normalized_fields, validation_errors FROM app.import_rows")
    assert row.normalized_fields == {}
    assert row.validation_errors == [{"code": "missing_facility", "field": "clinic_name", "severity": "error"}]
    assert result["rows"][0]["reasons"] == ["missing_facility"]


def test_result_does_not_echo_values_of_accepted_or_rejected_rows(signed_in):
    _, result = imported(signed_in, xlsx(CONTRACT_SHEETS))

    shown = str({ref: row for ref, row in rows_by_ref(result).items() if row["result"] != "needs_review"})
    for private in ("Pinecrest Clinic", "0917 000 0202", "missing-facility@example.test", "Other Street"):
        assert private not in shown


def test_blank_rows_between_data_are_counted_as_skipped(signed_in):
    _, result = imported(signed_in, xlsx({LJS: {1: {"C": "Clinic One"}, 3: {"C": "Clinic Two"}}}))

    assert result["counts"]["skipped_rows"] == 1
    assert rows_by_ref(result)[(LJS, 2)]["result"] == "skipped"
    assert result["state"] == "completed"


def test_changed_layout_is_rejected_with_the_contract_error_and_writes_nothing(signed_in, run_sql):
    response = upload(signed_in, xlsx({JACKS: {1: {"A": "Clinic", "B": "Phone"}, 2: {"A": "Clinic One"}}}))

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "unsupported_workbook_format"
    assert body["error"]["message"] == "Workbook layout needs review"
    assert "Clinic One" not in response.text
    assert run_sql("SELECT count(*) FROM app.import_batches")[0][0] == 0


def test_an_exported_lead_list_is_not_accepted_as_the_legacy_format(signed_in):
    response = upload(signed_in, xlsx({"SolNexus lead export v1": {1: {"A": "lead_id", "B": "record_type"}}}))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_workbook_format"


def test_only_xlsx_files_are_accepted(signed_in):
    response = upload(signed_in, b"name,email\n", filename="leads.csv")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_a_file_that_is_not_a_workbook_is_rejected(signed_in):
    response = upload(signed_in, b"not a zip", filename="leads.xlsx")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_workbook"


def test_missing_file_field_is_a_validation_error(signed_in):
    response = signed_in.post("/api/v1/imports", files={"other": ("x.xlsx", b"x", XLSX_TYPE)})

    assert response.status_code == 422
    assert response.json()["error"]["details"] == [{"field": "file", "message": "Field required"}]


def test_oversized_upload_is_refused_before_parsing(signed_in):
    response = signed_in.post(
        "/api/v1/imports",
        content=b"x",
        headers={"Content-Type": "multipart/form-data; boundary=b", "Content-Length": str(11 * 1024 * 1024)},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "workbook_too_large"


def test_upload_without_a_session_is_rejected_and_writes_nothing(client, run_sql):
    response = upload(client, xlsx(CONTRACT_SHEETS))

    assert response.status_code == 401
    assert run_sql("SELECT count(*) FROM app.import_batches")[0][0] == 0


def test_result_without_a_session_is_rejected(client, signed_in):
    accepted, _ = imported(signed_in, xlsx({LJS: ljs({"C": "Clinic One"})}))
    signed_in.post("/api/v1/auth/logout")

    response = client.get(f"/api/v1/imports/{accepted['batch_id']}")

    assert response.status_code == 401


def test_unknown_batch_is_not_found(signed_in):
    response = signed_in.get("/api/v1/imports/00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_a_failed_import_rolls_back_and_leaves_a_failed_batch(signed_in, run_sql, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr("app.imports.service.insert_status_baselines", broken)

    response = upload(signed_in, xlsx({JACKS: jacks({"C": "Clinic One", "H": "Contacted"})}))

    assert response.status_code == 500
    assert run_sql("SELECT state FROM app.import_batches") == [("failed",)]
    assert run_sql("SELECT count(*) FROM app.clinics")[0][0] == 0
    assert run_sql("SELECT count(*) FROM app.import_rows")[0][0] == 0


def test_a_corrupt_archive_is_an_invalid_workbook_not_a_server_error(signed_in, run_sql):
    corrupt = xlsx({LJS: ljs({"C": "Clinic One"})}).replace(b"PK\x01\x02", b"PK\x01\x00", 1)

    response = upload(signed_in, corrupt)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_workbook"
    assert run_sql("SELECT count(*) FROM app.import_batches")[0][0] == 0
