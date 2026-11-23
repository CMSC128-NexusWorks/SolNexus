import io
import zipfile

import pytest

from app.imports import workbook
from app.imports.workbook import WorkbookError, read_workbook
from tests.workbooks import CONTRACT_SHEETS, JACKS, LJS, xlsx


def test_reads_every_sheet_with_row_numbers_and_column_letters():
    sheets = read_workbook(xlsx(CONTRACT_SHEETS))

    assert [sheet.name for sheet in sheets] == [JACKS, LJS]
    ljs_rows = sheets[1].rows
    assert ljs_rows[0].number == 1
    assert ljs_rows[0].cells["C"] == "Harborview Clinic"
    assert ljs_rows[0].cells["I"] == "Sam Example"


def test_keeps_blank_rows_between_data_but_drops_trailing_ones():
    sheets = read_workbook(xlsx({LJS: {1: {"C": "Clinic One"}, 2: {"C": "   "}, 4: {"C": "Clinic Two"}, 9: {"C": ""}}}))

    rows = sheets[0].rows
    assert [row.number for row in rows] == [1, 2, 3, 4]
    assert [row.is_blank for row in rows] == [False, True, True, False]


def test_keeps_numeric_cells_typed_so_adapters_can_flag_them():
    sheets = read_workbook(xlsx({LJS: {1: {"C": "Clinic One", "D": 9170000101}}}))

    assert sheets[0].rows[0].cells["D"] == 9170000101


def test_rejects_a_file_that_is_not_a_workbook():
    with pytest.raises(WorkbookError) as error:
        read_workbook(b"name,email\nClinic,clinic@example.test\n")

    assert error.value.code == "invalid_workbook"


def test_rejects_a_zip_that_is_not_a_workbook():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", "hello")

    with pytest.raises(WorkbookError) as error:
        read_workbook(buffer.getvalue())

    assert error.value.code == "invalid_workbook"


def test_rejects_a_macro_enabled_workbook():
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(xlsx({LJS: {1: {"C": "Clinic One"}}}))) as source, zipfile.ZipFile(buffer, "w") as copy:
        for entry in source.infolist():
            copy.writestr(entry, source.read(entry))
        copy.writestr("xl/vbaProject.bin", b"\x00")

    with pytest.raises(WorkbookError) as error:
        read_workbook(buffer.getvalue())

    assert error.value.code == "invalid_workbook"


def test_rejects_an_upload_over_the_size_limit(monkeypatch):
    data = xlsx({LJS: {1: {"C": "Clinic One"}}})
    monkeypatch.setattr(workbook, "MAX_UPLOAD_BYTES", len(data) - 1)

    with pytest.raises(WorkbookError) as error:
        read_workbook(data)

    assert (error.value.code, error.value.status_code) == ("workbook_too_large", 413)


def test_rejects_an_archive_that_expands_past_the_limit(monkeypatch):
    # A zip bomb: small on the wire, huge once decompressed. Checked before openpyxl expands anything.
    data = xlsx({LJS: {1: {"C": "Clinic One"}}})
    monkeypatch.setattr(workbook, "MAX_UNCOMPRESSED_BYTES", 1_000)

    with pytest.raises(WorkbookError) as error:
        read_workbook(data)

    assert (error.value.code, error.value.status_code) == ("workbook_too_large", 413)


def test_rejects_more_populated_rows_than_the_limit(monkeypatch):
    monkeypatch.setattr(workbook, "MAX_POPULATED_ROWS", 2)

    with pytest.raises(WorkbookError) as error:
        read_workbook(xlsx({LJS: {1: {"C": "A"}, 2: {"C": "B"}}, JACKS: {1: {"A": "Facility"}}}))

    assert error.value.code == "too_many_rows"


def test_rejects_an_xml_entity_expansion_payload():
    # "Billion laughs": defusedxml refuses any DTD entity declaration instead of expanding it.
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(xlsx({LJS: {1: {"C": "Clinic One"}}}))) as source, zipfile.ZipFile(buffer, "w") as copy:
        for entry in source.infolist():
            content = source.read(entry)
            if entry.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(
                    b"<worksheet", b'<!DOCTYPE worksheet [<!ENTITY lol "lol">]><worksheet', 1
                )
            copy.writestr(entry, content)

    with pytest.raises(WorkbookError) as error:
        read_workbook(buffer.getvalue())

    assert error.value.code == "invalid_workbook"
    # openpyxl wraps the parser error; make sure defusedxml is what refused it, not some other failure.
    causes, exc = [], error.value
    while exc is not None:
        causes.append(type(exc).__name__)
        exc = exc.__cause__ or exc.__context__
    assert "EntitiesForbidden" in causes


def test_rejects_a_zip_with_a_corrupt_central_directory():
    # is_zipfile only finds the end-of-archive record, so this passes it and must still be a 422, not a 500.
    data = xlsx({LJS: {1: {"C": "Clinic One"}}})
    corrupt = data.replace(b"PK\x01\x02", b"PK\x01\x00", 1)
    assert zipfile.is_zipfile(io.BytesIO(corrupt))

    with pytest.raises(WorkbookError) as error:
        read_workbook(corrupt)

    assert (error.value.code, error.value.status_code) == ("invalid_workbook", 422)


def test_reads_past_a_stale_sheet_dimension():
    # Some writers store a <dimension> smaller than the data; read-only openpyxl would clip to it.
    buffer = io.BytesIO()
    source_data = xlsx({LJS: {1: {"C": "Clinic One"}, 2: {"C": "Clinic Two", "E": "two@example.test"}}})
    with zipfile.ZipFile(io.BytesIO(source_data)) as source, zipfile.ZipFile(buffer, "w") as copy:
        for entry in source.infolist():
            content = source.read(entry)
            if entry.filename == "xl/worksheets/sheet1.xml":
                assert b'<dimension ref="C1:E2" />' in content
                content = content.replace(b'<dimension ref="C1:E2" />', b'<dimension ref="A1:A1" />')
            copy.writestr(entry, content)

    (sheet,) = read_workbook(buffer.getvalue())

    assert [row.cells for row in sheet.rows] == [{"C": "Clinic One"}, {"C": "Clinic Two", "E": "two@example.test"}]


def test_a_stray_cell_far_below_the_data_fails_fast_instead_of_staging_a_million_blank_rows():
    # A few-KB file: A1 and the last row Excel allows. Each gap row would otherwise be staged and written
    # to the ledger as skipped, all in one transaction.
    data = xlsx({LJS: {1: {"C": "Clinic One"}, 1_048_576: {"C": "Clinic Two"}}})

    with pytest.raises(WorkbookError) as error:
        read_workbook(data)

    assert error.value.code == "too_many_rows"
    assert error.value.details == [{"field": "sheet 1", "reason": "data_below_row_limit"}]


def test_data_up_to_the_row_limit_is_read_with_its_gap_rows(monkeypatch):
    monkeypatch.setattr(workbook, "MAX_SHEET_ROW", 5)

    (sheet,) = read_workbook(xlsx({LJS: {1: {"C": "Clinic One"}, 5: {"C": "Clinic Two"}}}))

    assert [(row.number, row.is_blank) for row in sheet.rows] == [(1, False), (2, True), (3, True), (4, True), (5, False)]


def test_data_past_the_row_limit_is_refused(monkeypatch):
    monkeypatch.setattr(workbook, "MAX_SHEET_ROW", 5)

    with pytest.raises(WorkbookError) as error:
        read_workbook(xlsx({JACKS: {1: {"A": "Facility"}}, LJS: {1: {"C": "Clinic One"}, 6: {"C": "Clinic Two"}}}))

    assert error.value.details == [{"field": "sheet 2", "reason": "data_below_row_limit"}]
