"""Build a small, deterministic XLSX fixture shaped like the two private sheets.

The rows below are invented. Keep client workbook values out of this file.
Run: python3 docs/contracts/fixtures/build_synthetic_workbook.py
"""

from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


OUTPUT = Path(__file__).with_name("synthetic-lead-import-v1.xlsx")

JACKS = [
    {
        "A": "Facility", "B": "Name", "C": "Email", "D": "Status",
        "H": "Status", "I": "Next Step", "J": "Contact", "K": "Point Person",
    },
    # Data rows follow the Ljs A-G layout under the misleading header (data contract, Jacks layout evidence).
    {
        "A": "Region Sample", "B": "Province Sample", "C": "Harborview Clinic",
        "D": "0917 000 0199", "E": "harborview@example.test", "F": "Sample Street", "G": "Sample City",
        "H": "Contacted", "I": "Call next week",
        "J": "unmapped contact example", "K": "Staff Example",
    },
    {"A": "Region Sample", "C": "", "E": "missing-facility@example.test", "H": "Contacted"},
    {"A": "Region Sample", "C": "Pinecrest Clinic", "D": "0917 000 0202", "E": "pinecrest@example.test"},
]

LJS = [
    {
        "A": "Region Sample", "B": "Province Sample", "C": "Harborview Clinic",
        "D": "0917 000 0101", "E": "harborview@example.test",
        "F": "Sample Street", "G": "Sample City",
        "H": "Asked for a follow-up email", "I": "Sam Example",
    },
    {"A": "Region Sample", "B": "Province Sample", "C": "", "D": "0917 000 0303"},
    {
        "A": "Region Sample", "B": "Province Sample", "C": "Riverside Clinic",
        "D": "0917 000 0404", "E": "riverside@example.test",
        "F": "Other Street", "G": "Other City",
    },
]


def worksheet_xml(rows):
    xml_rows = []
    for row_number, fields in enumerate(rows, 1):
        cells = []
        for column, value in fields.items():
            cell = f"{column}{row_number}"
            safe_value = escape(value)
            cells.append(f'<c r="{cell}" t="inlineStr"><is><t>{safe_value}</t></is></c>')
        xml_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )


PARTS = {
    "[Content_Types].xml": (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    ),
    "_rels/.rels": (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    ),
    "xl/workbook.xml": (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Jacks Calling Sheet" sheetId="1" r:id="rId1"/>'
        '<sheet name="Ljs Calling Sheet" sheetId="2" r:id="rId2"/></sheets></workbook>'
    ),
    "xl/_rels/workbook.xml.rels": (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        '</Relationships>'
    ),
    "xl/worksheets/sheet1.xml": worksheet_xml(JACKS),
    "xl/worksheets/sheet2.xml": worksheet_xml(LJS),
}


def main():
    with ZipFile(OUTPUT, "w") as workbook:
        for name, content in PARTS.items():
            info = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            workbook.writestr(info, content.encode("utf-8"))
    print(OUTPUT)


if __name__ == "__main__":
    main()
