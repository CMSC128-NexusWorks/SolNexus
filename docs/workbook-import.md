# Legacy workbook import

SolTech's lead workbook seeds SolNexus once (FR-02). After migration, SolNexus is the source of truth: staff edit leads in the dashboard, and the workbook is never synced back. This page covers what the importer does, how staff resolve what it will not decide alone, and how to operate it. The rules it implements are in the [data/API contract](contracts/phase1-data-api-v1.md#workbook-migration-fr-02); the code is in [backend/app/imports](../backend/app/imports).

## Endpoints

All require a signed-in staff session.

| Method/path | Body | Success |
|---|---|---|
| `POST /api/v1/imports` | Multipart field `file`: the `.xlsx` workbook | `202` `{batch_id, state, replayed}` |
| `GET /api/v1/imports/{batch_id}` | None | `200` counts, one result per attempted row, open and resolved field reviews |
| `POST /api/v1/imports/{batch_id}/decisions` | `import_row_ids`, `action` (`create_clinic`, `link_clinic`, `reject`), `clinic_id` for `link_clinic`, optional `clinic_name` for `create_clinic`, `reason` | `200` updated batch |
| `POST /api/v1/imports/field-reviews/{review_id}/resolve` | `value` (string or null), `reason`, `clinic_version` as returned with the review | `200` resolved review |

Examples generated from real responses are in [phase1-api-examples-v1.json](contracts/fixtures/phase1-api-examples-v1.json) under `import`. The upload is processed before the `202` returns, so the batch is already final. The poll endpoint exists for the result screen and for the contract's asynchronous shape.

| Error | Status | Meaning |
|---|---|---|
| `length_required` | 411 | The upload has no `Content-Length` header (for example a chunked body), so its size cannot be bounded before it is read |
| `workbook_too_large` | 413 | Over 10 MiB, or the archive expands past 100 MiB or 1,000 entries |
| `too_many_rows` | 422 | Over 10,000 populated rows across both sheets, or data below row 20,000 of a sheet (usually a stray cell far down; delete it and upload again) |
| `invalid_workbook` | 422 | Not an `.xlsx` file, a corrupt archive, unreadable, macro-enabled, or contains XML entity declarations |
| `unsupported_file_type` | 422 | File name does not end in `.xlsx` |
| `unsupported_workbook_format` | 422 | Unknown sheet, changed Jacks header, or data in a column the adapter does not know. `details` names the sheet position or cell, never a value |
| `clinic_name_conflict` | 422 | `create_clinic` over rows that spell the name differently; send `clinic_name` |
| `rows_not_in_batch`, `unknown_clinic` | 422 | The decision names rows of another batch, or a clinic that does not exist |
| `row_already_decided`, `review_already_resolved` | 409 | The other staff member got there first; reload the batch |
| `version_conflict` | 409 | The clinic changed (for example, a dashboard edit) after the review was loaded; reload and decide again |

## What happens to each row

Both sheets are read by explicitly versioned adapters. `ljs-v1` is positional and reads row 1 as data. `jacks-v1` requires the observed header text in row 1 but maps the data positions, which follow the Ljs layout (see *Jacks layout evidence* in the contract; **awaiting SolTech confirmation**).

1. **Same file again** (identical SHA-256, read by the same adapter versions): the earlier batch is returned with `replayed: true`. Nothing is written. After an adapter version change, the same file is processed again.
2. **Blank row** between data rows: `skipped`. **Missing facility, invalid email or an overlong value:** `rejected` with a code. The ledger keeps codes only, no values.
3. **Same row seen before** (equal fingerprint: adapter version, sheet, row number and values): if it was accepted, it is `accepted` as `prior_import` and linked to the same clinic, with no field written. If staff rejected it, it is rejected again. An edited or moved row has a new fingerprint and goes through step 4.
4. **New row that may duplicate another row, an existing clinic, or a row of an earlier upload that still awaits review:** `needs_review`. Nothing is created or merged.
5. **Any other new row:** a new clinic (`origin = 'import'`). A mapped status is stored as an `import_baseline` status event, an observation and not a dated transition.

Warnings do not block a row: `unmapped_status` (status text with no approved code; status stays null), `numeric_contact_number` (Excel stored the phone as a number, so a leading zero may already be lost) and `unconfirmed_columns_held` (Jacks `J`/`K` kept as restricted evidence).

### Duplicate candidates (`candidates-v1`)

A row is paired with other rows of the upload, from either sheet, with every existing clinic, and with rows of earlier uploads still in `needs_review`, on four exact keys, each reported as a `basis`:

| Basis | Match |
|---|---|
| `exact_name` | Names equal after case folding and removing accents, punctuation and extra spaces |
| `similar_name` | Names equal after also dropping generic words (clinic, medical, center, hospital, ...) and spaces |
| `shared_email` | Same email, case-insensitive |
| `shared_phone` | Same last 10 digits (`0917 000 0101` = `+63 917 000 0101`); shorter numbers are ignored |

There is no fuzzy score or threshold: the contract has approved none, and an exact key tells staff why two rows were paired. Typos that survive these keys are not caught, so staff should reconcile the remaining rows before a production migration is accepted. Rows of one upload connected through row-to-row candidates share a `review_group` and should be decided together. Once a candidate row is accepted, its candidate entry also carries the `clinic_id` and `clinic_name` it now belongs to, so a group decided in parts can be linked to that clinic instead of created twice.

## Staff review

- **Same clinic, new:** `create_clinic` with all rows of the group. Values one row supplies, or that the rows agree on, are filled. Values they disagree on stay empty and open a **field review** listing each row's value, so neither sheet wins. A disagreeing name must be chosen in `clinic_name`.
- **An existing clinic:** `link_clinic` with its `clinic_id`. Existing values never change. Fields staff edited, cleared or settled in a resolved review keep their value and ignore the rows, even when an import review on that field is still open. Otherwise a field with an open review gets the rows added to it. Otherwise a blank field is filled when the rows agree, and any disagreement opens a field review. `contact_person` (from Ljs `I`) only fills a blank and never opens its own review.
- **Different clinics:** `create_clinic` for each row separately.
- **Not a lead:** `reject`. The row's values are dropped from the ledger.

Resolving a field review is a dashboard row edit. The value passes the same rules as the row editor, and the clinic field changes with the same audit trail (a `clinic_field_events` row, plus a `row_edit` status event for status). Each review shows the clinic's `current_value` and `clinic_version`. Staff may have edited the field in the dashboard after the review opened, so the request sends that version back, and a newer edit makes it answer `409 version_conflict` instead of replacing it. Resolution does not read silver, so it works before the first silver publication. A batch stays `needs_review` while any of its rows awaits a decision or any field review over its rows is open. It then becomes `completed`.

## Operating it

- **Retry:** an upload is one transaction. If it fails, nothing is written except a `failed` batch row recording the attempt; upload the same file again. A failed batch is never treated as a replay.
- **Concurrency:** uploads, decisions and review resolutions share one advisory lock (`IMPORT_LOCK_KEY`), so a double click or both staff uploading together import the file once.
- **Privacy:** values never appear in error responses or logs. Unhandled database errors are logged as class, SQLSTATE, table and constraint only, because PostgreSQL's error detail repeats the failing row. `app.import_rows.normalized_fields` keeps values only for accepted and `needs_review` rows; the retention period is still an open approval.
- **Limits:** 10 MiB and 10,000 populated rows are the contract's proposed limits. Data must sit within the first 20,000 rows of a sheet, because the blank rows between data rows are recorded as skipped; this bounds the work for an upload with a stray cell far down a sheet. Uploads must declare a `Content-Length` (browsers do), which the server enforces as the body size; a request-size limit in front of the API in deployment is still good practice.

## Real workbook dry run (October 30, 2026)

Run against a throwaway database that was dropped afterwards. Only counts were printed, never values.

| Measure | Result |
|---|---|
| Data rows | Jacks 587 + 2 blank, Ljs 50 |
| Created clinics | 502 |
| `needs_review` rows | 133, in 64 review groups (mostly pairs); only 2 rows pair across sheets |
| Rejected | 2 (missing facility) |
| Time | 0.25 s to parse and stage, 0.23 s to write |
| Status | 0 of 537 nonblank Jacks `H` values match an approved status label; all stay null with `unmapped_status` |
| Phone cells stored as numbers | 399 (`numeric_contact_number`) |

## Open before a production import

1. SolTech confirms the inferred Jacks `A`–`C` and `E`–`G` meanings.
2. SolTech approves a values-to-status mapping for Jacks `H`. Until then, every imported status is null.
3. Meanings for Jacks `J` and `K`, the retention period for import evidence, and the upload limits.
4. Staff reconcile the 64 review groups and any duplicates the exact keys miss.

## Tests

`docker compose run --rm api pytest tests/test_import_*.py`. The workbooks are synthetic and built in memory ([tests/workbooks.py](../backend/tests/workbooks.py)). `CONTRACT_SHEETS` holds the same rows as the contract fixture.
