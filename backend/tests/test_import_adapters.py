import pytest

from app.imports.adapters import JACKS_SHEET, LJS_SHEET, stage_workbook
from app.imports.workbook import WorkbookError, read_workbook
from tests.workbooks import CONTRACT_SHEETS, JACKS, JACKS_HEADER, LJS, jacks, ljs, xlsx


def stage(sheets):
    return stage_workbook(read_workbook(xlsx(sheets)))


def by_ref(rows):
    return {(row.sheet_name, row.row_number): row for row in rows}


def codes(row):
    return {issue.code for issue in row.issues}


def test_ljs_row_1_is_data_with_notes_and_person_spoken_to_in_their_own_fields():
    row = by_ref(stage(CONTRACT_SHEETS))[(LJS_SHEET, 1)]

    assert row.result == "valid"
    assert row.adapter_version == "ljs-v1"
    assert row.fields == {
        "region": "Region Sample",
        "province": "Province Sample",
        "clinic_name": "Harborview Clinic",
        "contact_number": "0917 000 0101",
        "email": "harborview@example.test",
        "address": "Sample Street",
        "municipality": "Sample City",
        "calling_notes": "Asked for a follow-up email",
        "person_spoken_to": "Sam Example",
        # I initializes the empty contact person, never the clinic name.
        "contact_person": "Sam Example",
    }


def test_jacks_maps_its_data_columns_not_its_header_labels():
    # Header row says A Facility, C Email, D Status; the data is region, clinic name and phone there.
    row = by_ref(stage(CONTRACT_SHEETS))[(JACKS_SHEET, 2)]

    assert row.result == "valid"
    assert row.adapter_version == "jacks-v1"
    assert row.fields == {
        "region": "Region Sample",
        "province": "Province Sample",
        "clinic_name": "Harborview Clinic",
        "contact_number": "0917 000 0199",
        "email": "harborview@example.test",
        "address": "Sample Street",
        "municipality": "Sample City",
        "status_code": "contacted",
        "next_step": "Call next week",
    }


def test_jacks_unconfirmed_columns_are_held_as_evidence_not_mapped():
    row = by_ref(stage(CONTRACT_SHEETS))[(JACKS_SHEET, 2)]

    assert row.unmapped == {"contact": "unmapped contact example", "point_person": "Staff Example"}
    assert "contact_person" not in row.fields and "point_person" not in row.fields
    assert "unconfirmed_columns_held" in codes(row)


def test_jacks_header_row_is_not_staged_as_data():
    refs = by_ref(stage(CONTRACT_SHEETS))

    assert (JACKS_SHEET, 1) not in refs
    assert sorted(number for sheet, number in refs if sheet == JACKS_SHEET) == [2, 3, 4]


def test_rows_without_a_facility_are_rejected_on_both_sheets():
    refs = by_ref(stage(CONTRACT_SHEETS))

    for ref in [(JACKS_SHEET, 3), (LJS_SHEET, 2)]:
        assert refs[ref].result == "rejected"
        assert "missing_facility" in codes(refs[ref])


def test_sheet_order_does_not_change_staging():
    reversed_order = {LJS: CONTRACT_SHEETS[LJS], JACKS: CONTRACT_SHEETS[JACKS]}

    assert by_ref(stage(reversed_order)) == by_ref(stage(CONTRACT_SHEETS))


@pytest.mark.parametrize("raw", ["Contacted", "  CONTACTED ", "contacted", "follow-up needed", "proposal_sent"])
def test_status_maps_only_exact_approved_codes_or_labels(raw):
    row = stage({JACKS: jacks({"C": "Clinic One", "H": raw})})[0]

    assert row.fields["status_code"] in {"contacted", "follow_up_needed", "proposal_sent"}
    assert "unmapped_status" not in codes(row)


@pytest.mark.parametrize("raw", ["Interested", "contacted?", "Demo booked", "closed - won"])
def test_unapproved_status_text_stays_null_and_is_flagged_for_review(raw):
    row = stage({JACKS: jacks({"C": "Clinic One", "H": raw})})[0]

    assert row.result == "valid"
    assert "status_code" not in row.fields
    assert row.unmapped["status"] == raw
    assert "unmapped_status" in codes(row)


def test_next_step_prose_never_becomes_a_date():
    row = stage({JACKS: jacks({"C": "Clinic One", "I": "Call back 2026-11-03"})})[0]

    assert row.fields["next_step"] == "Call back 2026-11-03"
    assert "next_action_date" not in row.fields


def test_numeric_phone_cell_is_kept_as_text_and_flagged():
    row = stage({LJS: ljs({"C": "Clinic One", "D": 9170000101})})[0]

    assert row.fields["contact_number"] == "9170000101"
    assert "numeric_contact_number" in codes(row)
    assert row.result == "valid"


def test_text_phone_keeps_its_leading_zero():
    row = stage({LJS: ljs({"C": "Clinic One", "D": "09170000101"})})[0]

    assert row.fields["contact_number"] == "09170000101"
    assert "numeric_contact_number" not in codes(row)


@pytest.mark.parametrize("email", ["not-an-email", "a@example.test / b@example.test", "a@b"])
def test_invalid_email_rejects_the_whole_row(email):
    row = stage({LJS: ljs({"C": "Clinic One", "E": email})})[0]

    assert row.result == "rejected"
    assert "invalid_email" in codes(row)


def test_email_is_trimmed_and_lowercased():
    row = stage({LJS: ljs({"C": "Clinic One", "E": "  Front.Desk@Example.TEST "})})[0]

    assert row.fields["email"] == "front.desk@example.test"


def test_overlong_value_rejects_the_row():
    row = stage({LJS: ljs({"C": "Clinic One", "H": "x" * 2_001})})[0]

    assert row.result == "rejected"
    assert "value_too_long" in codes(row)


def test_blank_rows_between_data_are_skipped():
    rows = stage({LJS: {1: {"C": "Clinic One"}, 3: {"C": "Clinic Two"}}})

    assert [(row.row_number, row.result) for row in rows] == [(1, "valid"), (2, "skipped"), (3, "valid")]


def test_issues_never_carry_cell_values():
    rows = stage({LJS: ljs({"C": "Clinic One", "E": "secret-value"}), JACKS: jacks({"C": "Clinic Two", "H": "odd status"})})

    for row in rows:
        for issue in row.issues:
            assert set(issue.as_json()) == {"code", "field", "severity"}
            assert "secret-value" not in str(issue.as_json()) and "odd status" not in str(issue.as_json())


def test_fingerprint_changes_with_content_or_position_but_not_between_reads():
    first = stage({LJS: ljs({"C": "Clinic One"}, {"C": "Clinic Two"})})
    again = stage({LJS: ljs({"C": "Clinic One"}, {"C": "Clinic Two"})})
    edited = stage({LJS: ljs({"C": "Clinic One", "D": "0917 000 0001"}, {"C": "Clinic Two"})})
    moved = stage({LJS: ljs({"C": "Clinic Two"}, {"C": "Clinic One"})})

    assert [row.fingerprint for row in first] == [row.fingerprint for row in again]
    assert first[0].fingerprint != edited[0].fingerprint
    assert first[1].fingerprint == edited[1].fingerprint
    assert first[0].fingerprint != moved[1].fingerprint


def test_unknown_sheet_fails_the_upload_without_naming_its_contents():
    with pytest.raises(WorkbookError) as error:
        stage({LJS: ljs({"C": "Clinic One"}), "Lead export v1": {1: {"A": "lead_id"}}})

    assert error.value.code == "unsupported_workbook_format"
    assert error.value.details == [{"field": "sheet 2", "reason": "unknown_sheet"}]


def test_changed_jacks_header_fails_the_upload():
    header = {**JACKS_HEADER, "D": "Phone"}

    with pytest.raises(WorkbookError) as error:
        stage({JACKS: {1: header, 2: {"C": "Clinic One"}}})

    assert error.value.code == "unsupported_workbook_format"
    assert error.value.details == [{"field": f"{JACKS_SHEET}!D1", "reason": "unexpected_header"}]


def test_jacks_without_its_header_row_fails_rather_than_reading_row_1_as_data():
    with pytest.raises(WorkbookError) as error:
        stage({JACKS: {1: {"C": "Clinic One", "E": "one@example.test"}}})

    assert error.value.code == "unsupported_workbook_format"


def test_data_in_an_unknown_column_fails_the_upload():
    with pytest.raises(WorkbookError) as error:
        stage({LJS: ljs({"C": "Clinic One", "J": "extra"})})

    assert error.value.details == [{"field": f"{LJS_SHEET}!J", "reason": "unexpected_column"}]


def test_a_single_known_sheet_is_accepted():
    rows = stage({LJS: ljs({"C": "Clinic One"})})

    assert [row.result for row in rows] == ["valid"]
