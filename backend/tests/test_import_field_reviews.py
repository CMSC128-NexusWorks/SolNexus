"""Resolving import field reviews: staff choose the value the workbook rows disagreed on."""

from tests.workbooks import CONTRACT_SHEETS, JACKS, LJS, jacks, xlsx

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def import_and_confirm(client, sheets, refs):
    """Upload, then confirm the rows at refs as one new clinic; return the result with its field reviews."""
    response = client.post("/api/v1/imports", files={"file": ("leads.xlsx", xlsx(sheets), XLSX_TYPE)})
    batch = client.get(f"/api/v1/imports/{response.json()['batch_id']}").json()
    rows = {(row["sheet"], row["row"]): row for row in batch["rows"]}
    decision = client.post(
        f"/api/v1/imports/{batch['batch_id']}/decisions",
        json={"import_row_ids": [rows[ref]["import_row_id"] for ref in refs], "action": "create_clinic", "reason": "Same clinic"},
    )
    assert decision.status_code == 200, decision.text
    return decision.json()


def resolve(client, review, value, reason="Called the clinic", clinic_version=None):
    """Resolve with the clinic version the review reported, as the review screen will."""
    body = {"value": value, "reason": reason, "clinic_version": clinic_version or review.get("clinic_version") or 1}
    return client.post(f"/api/v1/imports/field-reviews/{review['review_id']}/resolve", json=body)


def contract_review(client):
    result = import_and_confirm(client, CONTRACT_SHEETS, [(LJS, 1), (JACKS, 2)])
    (review,) = result["field_reviews"]
    return result, review


def test_choosing_a_value_sets_the_field_with_an_audit_event_and_completes_the_batch(signed_in, staff, run_sql):
    result, review = contract_review(signed_in)
    (before,) = run_sql("SELECT version FROM app.clinics WHERE clinic_id = :id", id=review["clinic_id"])

    response = resolve(signed_in, review, " 0917 000 0199 ")

    assert response.status_code == 200
    assert (response.json()["state"], response.json()["resolved_value"]) == ("resolved", "0917 000 0199")
    (clinic,) = run_sql("SELECT contact_number, version FROM app.clinics WHERE clinic_id = :id", id=review["clinic_id"])
    assert (clinic.contact_number, clinic.version) == ("0917 000 0199", before.version + 1)
    (event,) = run_sql("SELECT * FROM app.clinic_field_events WHERE clinic_id = :id", id=review["clinic_id"])
    assert (event.field_name, event.old_value, event.new_value) == ("contact_number", None, "0917 000 0199")
    assert (str(event.changed_by), event.reason) == (staff["user_id"], "Called the clinic")
    (stored,) = run_sql("SELECT resolved_by, resolution_reason FROM app.import_field_reviews")
    assert (str(stored.resolved_by), stored.resolution_reason) == (staff["user_id"], "Called the clinic")
    batch = signed_in.get(f"/api/v1/imports/{result['batch_id']}").json()
    assert batch["state"] == "completed"


def test_choosing_empty_resolves_without_writing_the_field(signed_in, run_sql):
    result, review = contract_review(signed_in)

    response = resolve(signed_in, review, None)

    assert response.status_code == 200
    assert (response.json()["state"], response.json()["resolved_value"]) == ("resolved", None)
    # JSON null, not SQL NULL: "staff chose empty" stays distinct from "not decided".
    assert run_sql("SELECT resolved_value IS NOT NULL, resolved_value = 'null'::jsonb FROM app.import_field_reviews") == [(True, True)]
    assert run_sql("SELECT contact_number FROM app.clinics WHERE clinic_id = :id", id=review["clinic_id"]) == [(None,)]
    assert run_sql("SELECT count(*) FROM app.clinic_field_events")[0][0] == 0
    assert signed_in.get(f"/api/v1/imports/{result['batch_id']}").json()["state"] == "completed"


def test_resolving_a_status_conflict_records_a_staff_status_event(signed_in, staff, run_sql):
    sheets = {JACKS: jacks({"C": "Clinic One", "H": "Contacted"}, {"C": "Clinic One", "H": "Closed"})}
    result = import_and_confirm(signed_in, sheets, [(JACKS, 2), (JACKS, 3)])
    (review,) = result["field_reviews"]
    assert review["field_name"] == "status_code"
    # No baseline while the workbook rows disagree.
    assert run_sql("SELECT count(*) FROM app.clinic_status_events")[0][0] == 0

    assert resolve(signed_in, review, "closed").status_code == 200

    (event,) = run_sql("SELECT * FROM app.clinic_status_events")
    assert (event.origin, event.old_status_code, event.new_status_code, str(event.changed_by)) == (
        "row_edit", None, "closed", staff["user_id"],
    )


def test_a_review_resolves_once(signed_in):
    _, review = contract_review(signed_in)
    resolve(signed_in, review, "0917 000 0101")

    response = resolve(signed_in, review, "0917 000 0199")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "review_already_resolved"


def test_a_resolved_value_must_pass_the_import_field_rules(signed_in):
    sheets = {JACKS: jacks({"C": "Clinic One", "H": "Contacted", "E": "a@example.test"},
                           {"C": "Clinic One", "H": "Closed", "E": "b@example.test"})}
    result = import_and_confirm(signed_in, sheets, [(JACKS, 2), (JACKS, 3)])
    reviews = {review["field_name"]: review for review in result["field_reviews"]}

    assert resolve(signed_in, reviews["status_code"], "Demo booked").status_code == 422
    assert resolve(signed_in, reviews["email"], "not an email").status_code == 422
    # Stored as entered, as a dashboard edit would store it.
    assert resolve(signed_in, reviews["email"], "Front.Desk@Example.TEST").json()["resolved_value"] == "Front.Desk@Example.TEST"


def test_a_reason_is_required(signed_in):
    _, review = contract_review(signed_in)

    response = resolve(signed_in, review, "0917 000 0101", reason="  ")

    assert response.status_code == 422


def test_unknown_review_is_not_found(signed_in):
    response = resolve(signed_in, {"review_id": "00000000-0000-4000-8000-000000000000"}, None)

    assert response.status_code == 404


def test_a_review_shows_the_clinic_value_and_version_to_resolve_against(signed_in, run_sql):
    _, review = contract_review(signed_in)

    (clinic,) = run_sql("SELECT version FROM app.clinics WHERE clinic_id = :id", id=review["clinic_id"])
    assert (review["current_value"], review["clinic_version"]) == (None, clinic.version)


def test_a_dashboard_edit_after_the_review_opened_is_never_silently_replaced(signed_in, run_sql):
    result, review = contract_review(signed_in)
    # Staff A sets the phone in the dashboard after the import opened the review. This is what
    # PATCH /clinics commits (its response reads silver, which this test does not build).
    run_sql(
        "UPDATE app.clinics SET contact_number = '0917 555 0100', version = version + 1 WHERE clinic_id = :id",
        id=review["clinic_id"],
    )
    run_sql(
        """INSERT INTO app.clinic_field_events (clinic_id, field_name, old_value, new_value, changed_by)
           SELECT :id, 'contact_number', 'null', '"0917 555 0100"', user_id FROM app.staff_users LIMIT 1""",
        id=review["clinic_id"],
    )

    # Staff B resolves from the review as they loaded it, before that edit.
    stale = resolve(signed_in, review, "0917 000 0199")

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    assert run_sql("SELECT contact_number FROM app.clinics WHERE clinic_id = :id", id=review["clinic_id"]) == [("0917 555 0100",)]
    # After reloading, staff B sees the edit and decides knowingly.
    (reloaded,) = signed_in.get(f"/api/v1/imports/{result['batch_id']}").json()["field_reviews"]
    assert (reloaded["state"], reloaded["current_value"]) == ("unresolved", "0917 555 0100")
    kept = resolve(signed_in, reloaded, "0917 555 0100", reason="Keep the number staff entered")
    assert (kept.status_code, kept.json()["state"]) == (200, "resolved")
    # Choosing the value already there writes no second audit row.
    assert run_sql("SELECT count(*) FROM app.clinic_field_events WHERE clinic_id = :id", id=review["clinic_id"])[0][0] == 1


def test_resolving_requires_the_clinic_version(signed_in):
    _, review = contract_review(signed_in)

    response = signed_in.post(
        f"/api/v1/imports/field-reviews/{review['review_id']}/resolve", json={"value": None, "reason": "Checked"}
    )

    assert response.status_code == 422
