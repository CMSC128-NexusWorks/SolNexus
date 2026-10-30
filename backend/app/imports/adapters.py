"""Versioned adapters that map each legacy worksheet's rows to clinic fields (data contract, FR-02).

The two sheets are equally authoritative but laid out differently, so each has its own adapter:

* Ljs Calling Sheet (ljs-v1): no header row, so row 1 is data. Positions A-I are confirmed.
* Jacks Calling Sheet (jacks-v1): header row 1 must match the observed header text, and data starts at
  row 2. Its header labels do not describe its data: the data rows use the Ljs A-G layout (region,
  province, clinic, phone, email, address, municipality), H is the real status, I is next step. See the
  data contract's "Jacks layout evidence" for how this was established without reading row values.

Only mapped columns become clinic fields. Columns whose meaning SolTech has not confirmed (Jacks J, K) and
status text with no approved mapping are kept as restricted evidence on the import row, never copied into
operational fields. A changed layout fails the whole upload instead of guessing.

Staging is per row and has no database access. Deciding which clinic a valid row belongs to happens later
(candidates.py, service.py), so this module never sees other rows or existing clinics.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Literal

from app.imports.workbook import CellValue, Sheet, SheetRow, WorkbookError

LJS_SHEET = "Ljs Calling Sheet"
JACKS_SHEET = "Jacks Calling Sheet"

# Long enough for real notes, short enough that a pasted document cannot sit in a clinic field.
MAX_FIELD_CHARS = 2_000

# Proposed Phase 1 status vocabulary and its dashboard labels (frontend STATUS_LABELS). Jacks H maps only
# on an exact, case-insensitive match to a code or a label; anything else stays null for staff review.
STATUS_LABELS = {
    "contacted": "Contacted",
    "proposal_sent": "Proposal sent",
    "awaiting_demo": "Awaiting demo",
    "follow_up_needed": "Follow-up needed",
    "closed": "Closed",
}
_APPROVED_STATUS_INPUTS = {
    **{code: code for code in STATUS_LABELS},
    **{label.casefold(): code for code, label in STATUS_LABELS.items()},
}

# Deliberately loose: it catches typos and two addresses in one cell, not every RFC 5322 corner case.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]+$")

StagedResult = Literal["valid", "rejected", "skipped"]


@dataclass(frozen=True)
class RowIssue:
    """A safe reason code for the import ledger. Never holds the cell value."""

    code: str
    field: str | None = None
    severity: Literal["error", "warning"] = "error"

    def as_json(self) -> dict:
        return {"code": self.code, "field": self.field, "severity": self.severity}


@dataclass(frozen=True)
class StagedRow:
    sheet_name: str
    row_number: int
    adapter_version: str
    result: StagedResult
    # Confirmed operational fields with a nonblank value, keyed by app.lead_field_name.
    fields: dict[str, str] = field(default_factory=dict)
    # Restricted evidence: unconfirmed columns and unmapped status text. Never written to app.clinics.
    unmapped: dict[str, str] = field(default_factory=dict)
    issues: tuple[RowIssue, ...] = ()
    fingerprint: str = ""

    @property
    def errors(self) -> list[RowIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]


def cell_text(value: CellValue | None) -> str | None:
    """Text for a cell, trimmed; None when blank. Excel stores phone numbers typed without a leading
    apostrophe as numbers, so 9170000101.0 becomes "9170000101" rather than a float string."""
    if value is None:
        return None
    if isinstance(value, bool):
        text = "TRUE" if value else "FALSE"
    elif isinstance(value, float) and value.is_integer():
        text = str(int(value))
    elif isinstance(value, (datetime, date, time)):
        text = value.isoformat()
    else:
        text = str(value)
    text = text.strip()
    return text or None


def row_fingerprint(adapter_version: str, sheet_name: str, row_number: int, fields: dict, unmapped: dict) -> str:
    """Identity of one row's content at one position, per the contract: adapter version, sheet, row and
    normalized values. Equal fingerprints mean "the same row again" for retry detection. It is never
    clinic identity: two different rows naming one clinic have different fingerprints."""
    payload = json.dumps(
        [adapter_version, sheet_name, row_number, fields, unmapped], sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _Adapter:
    sheet_name: str
    version: str
    # Column letter -> clinic field for confirmed columns.
    field_columns: dict[str, str]
    # Column letter -> evidence key for columns held for review.
    evidence_columns: dict[str, str] = {}
    first_data_row: int
    status_column: str | None = None

    @property
    def known_columns(self) -> set[str]:
        return set(self.field_columns) | set(self.evidence_columns) | ({self.status_column} - {None})

    def check_layout(self, sheet: Sheet) -> None:
        """Fail the upload when the sheet uses a column this adapter does not know: the layout changed,
        and mapping it by position could put values in the wrong fields."""
        unknown = sorted({column for row in sheet.rows for column in row.cells} - self.known_columns, key=_column_order)
        if unknown:
            raise WorkbookError(
                "unsupported_workbook_format",
                "Workbook layout needs review",
                details=[{"field": f"{sheet.name}!{column}", "reason": "unexpected_column"} for column in unknown],
            )

    def stage(self, row: SheetRow) -> StagedRow:
        if row.is_blank:
            return self._staged(row, "skipped", {}, {}, ())
        fields: dict[str, str] = {}
        unmapped: dict[str, str] = {}
        issues: list[RowIssue] = []

        for column, field_name in self.field_columns.items():
            text = cell_text(row.cells.get(column))
            if text is not None:
                fields[field_name] = text
        for column, key in self.evidence_columns.items():
            text = cell_text(row.cells.get(column))
            if text is not None:
                unmapped[key] = text
        if unmapped:
            issues.append(RowIssue("unconfirmed_columns_held", severity="warning"))

        if self.status_column is not None:
            raw_status = cell_text(row.cells.get(self.status_column))
            if raw_status is not None:
                code = _APPROVED_STATUS_INPUTS.get(" ".join(raw_status.split()).casefold())
                if code is not None:
                    fields["status_code"] = code
                else:
                    unmapped["status"] = raw_status
                    issues.append(RowIssue("unmapped_status", "status_code", "warning"))

        if "email" in fields:
            fields["email"] = fields["email"].lower()
            if not EMAIL_PATTERN.match(fields["email"]):
                issues.append(RowIssue("invalid_email", "email"))
        if isinstance(row.cells.get(self._column_of("contact_number")), (int, float)):
            # Stored as a number, so Excel already dropped any leading zero. Kept as text, flagged for staff.
            issues.append(RowIssue("numeric_contact_number", "contact_number", "warning"))
        for field_name, text in {**fields, **unmapped}.items():
            if len(text) > MAX_FIELD_CHARS:
                issues.append(RowIssue("value_too_long", field_name if field_name in fields else None))
        if "clinic_name" not in fields:
            issues.append(RowIssue("missing_facility", "clinic_name"))

        result: StagedResult = "rejected" if any(issue.severity == "error" for issue in issues) else "valid"
        return self._staged(row, result, fields, unmapped, tuple(issues))

    def _column_of(self, field_name: str) -> str | None:
        return next((column for column, name in self.field_columns.items() if name == field_name), None)

    def _staged(self, row, result, fields, unmapped, issues) -> StagedRow:
        return StagedRow(
            sheet_name=self.sheet_name,
            row_number=row.number,
            adapter_version=self.version,
            result=result,
            fields=fields,
            unmapped=unmapped,
            issues=issues,
            fingerprint=row_fingerprint(self.version, self.sheet_name, row.number, fields, unmapped),
        )

    def stage_sheet(self, sheet: Sheet) -> list[StagedRow]:
        self.check_layout(sheet)
        return [self.stage(row) for row in sheet.rows if row.number >= self.first_data_row]


class LjsAdapterV1(_Adapter):
    """Headerless and positional: row 1 is a clinic, never skipped as a header."""

    sheet_name = LJS_SHEET
    version = "ljs-v1"
    first_data_row = 1
    field_columns = {
        "A": "region",
        "B": "province",
        "C": "clinic_name",
        "D": "contact_number",
        "E": "email",
        "F": "address",
        "G": "municipality",
        "H": "calling_notes",
        "I": "person_spoken_to",
    }

    def stage(self, row: SheetRow) -> StagedRow:
        staged = super().stage(row)
        if staged.result != "valid" or "person_spoken_to" not in staged.fields:
            return staged
        # Contract: I may initialize contact_person while that field is empty. It is empty for any new
        # clinic, and service.py only fills a blank, never-edited field on an existing one.
        fields = {**staged.fields, "contact_person": staged.fields["person_spoken_to"]}
        return StagedRow(**{**staged.__dict__, "fields": fields})


class JacksAdapterV1(_Adapter):
    """Header-checked: row 1 must be the observed header text; data starts at row 2.

    The header text is checked but not used as meaning. Under the "Facility", "Name" and "Email" labels
    the data is region, province and clinic name; email sits under the unlabeled E. D's "Status" header
    holds contact numbers (confirmed October 19), and H is the status.
    """

    sheet_name = JACKS_SHEET
    version = "jacks-v1"
    first_data_row = 2
    field_columns = {
        "A": "region",
        "B": "province",
        "C": "clinic_name",
        "D": "contact_number",
        "E": "email",
        "F": "address",
        "G": "municipality",
        "I": "next_step",
    }
    status_column = "H"
    # Meanings not yet confirmed by SolTech (contact detail vs D; SolTech owner vs clinic contact).
    evidence_columns = {"J": "contact", "K": "point_person"}
    expected_header = {
        "A": "facility", "B": "name", "C": "email", "D": "status", "E": None, "F": None, "G": None,
        "H": "status", "I": "next step", "J": "contact", "K": "point person",
    }

    def check_layout(self, sheet: Sheet) -> None:
        super().check_layout(sheet)
        header = next((row for row in sheet.rows if row.number == 1), SheetRow(1, {}))
        mismatched = [
            column
            for column, expected in self.expected_header.items()
            if (cell_text(header.cells.get(column)) or "").casefold() != (expected or "")
        ]
        if mismatched:
            raise WorkbookError(
                "unsupported_workbook_format",
                "Workbook layout needs review",
                details=[{"field": f"{sheet.name}!{column}1", "reason": "unexpected_header"} for column in mismatched],
            )


ADAPTERS: dict[str, _Adapter] = {adapter.sheet_name: adapter for adapter in (LjsAdapterV1(), JacksAdapterV1())}


def stage_workbook(sheets: list[Sheet]) -> list[StagedRow]:
    """Stage every row of every known sheet. Any unknown sheet fails the upload, so an exported lead list
    or an unrelated workbook is never read as the legacy format. Sheet order does not matter."""
    unknown = [index for index, sheet in enumerate(sheets, start=1) if sheet.name not in ADAPTERS]
    if unknown or not sheets:
        raise WorkbookError(
            "unsupported_workbook_format",
            "Workbook layout needs review",
            details=[{"field": f"sheet {index}", "reason": "unknown_sheet"} for index in unknown],
        )
    staged: list[StagedRow] = []
    for sheet in sheets:
        staged.extend(ADAPTERS[sheet.name].stage_sheet(sheet))
    return staged


def _column_order(column: str) -> tuple[int, str]:
    return (len(column), column)
