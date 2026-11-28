import pytest

from app.imports.candidates import CandidateKeys, find_candidates, loose_name_key, name_key, phone_key, review_groups


def keys(name=None, email=None, phone=None):
    return CandidateKeys.from_fields({"clinic_name": name, "email": email, "contact_number": phone})


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Harborview Clinic", "HARBORVIEW  CLINIC"),
        ("St. Luke's Clinic", "St Lukes Clinic"),
        ("Peñafrancia Clinic", "Penafrancia Clinic"),
        ("Rivera & Sons Clinic", "Rivera and Sons Clinic"),
    ],
)
def test_exact_name_ignores_case_spacing_punctuation_and_accents(a, b):
    assert name_key(a) == name_key(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Harborview Medical Clinic", "Harbor View Clinic"),
        ("The Pinecrest Medical Center", "Pinecrest Hospital"),
    ],
)
def test_similar_name_also_ignores_generic_words_and_spaces(a, b):
    assert name_key(a) != name_key(b)
    assert loose_name_key(a) == loose_name_key(b)


def test_an_all_generic_name_never_pairs_by_similarity():
    assert loose_name_key("Medical Clinic") is None


@pytest.mark.parametrize("phone", ["0917 000 0101", "+63 917 000 0101", "9170000101", "(0917) 000-0101"])
def test_phone_key_compares_the_last_ten_digits(phone):
    assert phone_key(phone) == "9170000101"


def test_short_numbers_are_not_identity_evidence():
    assert phone_key("8123") is None


def test_rows_from_both_sheets_naming_one_clinic_are_candidates_of_each_other():
    found = find_candidates(
        [("ljs-1", keys("Harborview Clinic", "harborview@example.test", "0917 000 0101")),
         ("jacks-2", keys("Harborview Clinic", "harborview@example.test", "0917 000 0199"))],
        [],
    )

    assert found == {
        "ljs-1": {("row", "jacks-2"): ["exact_name", "shared_email"]},
        "jacks-2": {("row", "ljs-1"): ["exact_name", "shared_email"]},
    }


def test_a_row_matching_an_existing_clinic_lists_that_clinic():
    found = find_candidates([("ljs-3", keys("Riverside Clinic"))], [("clinic-9", keys("Riverside Medical Clinic"))])

    assert found == {"ljs-3": {("clinic", "clinic-9"): ["similar_name"]}}


def test_shared_contact_identifiers_alone_are_candidates():
    found = find_candidates(
        [("a", keys("Clinic One", phone="0917 000 0101")), ("b", keys("Clinic Two", email="shared@example.test"))],
        [("c", keys("Clinic Three", phone="+63 917 000 0101", email="shared@example.test"))],
    )

    assert found == {
        "a": {("clinic", "c"): ["shared_phone"]},
        "b": {("clinic", "c"): ["shared_email"]},
    }


def test_rows_with_nothing_in_common_have_no_candidates():
    assert find_candidates([("a", keys("Clinic One")), ("b", keys("Clinic Two"))], [("c", keys("Clinic Three"))]) == {}


def test_result_does_not_depend_on_row_order():
    rows = [("a", keys("Clinic One", "one@example.test")), ("b", keys("clinic one")), ("c", keys("Other", "one@example.test"))]

    assert find_candidates(rows, []) == find_candidates(list(reversed(rows)), [])


def test_review_groups_join_rows_connected_through_other_rows():
    found = find_candidates(
        [("a", keys("Clinic One")), ("b", keys("clinic one", phone="0917 000 0101")),
         ("c", keys("Other", phone="0917 000 0101")), ("d", keys("Lonely", email="x@example.test"))],
        [("clinic-1", keys("Something", email="x@example.test"))],
    )

    assert review_groups(found) == {"a": "a", "b": "a", "c": "a", "d": "d"}
