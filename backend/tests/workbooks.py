"""Build synthetic .xlsx workbooks in memory for import tests. Every value here is invented."""

from __future__ import annotations

import io

from openpyxl import Workbook

JACKS = "Jacks Calling Sheet"
LJS = "Ljs Calling Sheet"

JACKS_HEADER = {
    "A": "Facility", "B": "Name", "C": "Email", "D": "Status",
    "H": "Status", "I": "Next Step", "J": "Contact", "K": "Point Person",
}

# Mirrors docs/contracts/fixtures/build_synthetic_workbook.py, the contract fixture: headerless Ljs row 1,
# Jacks's misleading header row over Ljs-style data columns, missing facilities, and Harborview on both
# sheets with different phones.
CONTRACT_SHEETS = {
    JACKS: {
        1: JACKS_HEADER,
        2: {
            "A": "Region Sample", "B": "Province Sample", "C": "Harborview Clinic",
            "D": "0917 000 0199", "E": "harborview@example.test", "F": "Sample Street", "G": "Sample City",
            "H": "Contacted", "I": "Call next week", "J": "unmapped contact example", "K": "Staff Example",
        },
        3: {"A": "Region Sample", "C": "", "E": "missing-facility@example.test", "H": "Contacted"},
        4: {"A": "Region Sample", "C": "Pinecrest Clinic", "D": "0917 000 0202", "E": "pinecrest@example.test"},
    },
    LJS: {
        1: {
            "A": "Region Sample", "B": "Province Sample", "C": "Harborview Clinic",
            "D": "0917 000 0101", "E": "harborview@example.test",
            "F": "Sample Street", "G": "Sample City",
            "H": "Asked for a follow-up email", "I": "Sam Example",
        },
        2: {"A": "Region Sample", "B": "Province Sample", "C": "", "D": "0917 000 0303"},
        3: {
            "A": "Region Sample", "B": "Province Sample", "C": "Riverside Clinic",
            "D": "0917 000 0404", "E": "riverside@example.test",
            "F": "Other Street", "G": "Other City",
        },
    },
}


def xlsx(sheets: dict[str, dict[int, dict[str, object]]]) -> bytes:
    """Return workbook bytes with one worksheet per key, in the given order. Rows are {row: {column: value}}."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        worksheet = workbook.create_sheet(name)
        for row_number, cells in rows.items():
            for column, value in cells.items():
                worksheet[f"{column}{row_number}"] = value
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def jacks(*rows: dict[str, object]) -> dict[int, dict[str, object]]:
    """A Jacks sheet with the observed header in row 1 and the given data rows from row 2."""
    return {1: JACKS_HEADER, **{number: row for number, row in enumerate(rows, start=2)}}


def ljs(*rows: dict[str, object]) -> dict[int, dict[str, object]]:
    """An Ljs sheet: no header, so data starts at row 1."""
    return {number: row for number, row in enumerate(rows, start=1)}
