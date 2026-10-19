# Phase 1 data and API contract — proposed v1

Status: **implementation proposal for SNX-20**. The staff-confirmed message identity rule in [phase1-identity-v1.md](phase1-identity-v1.md) is already agreed. Product choices listed under **Approval gates** still need team/client confirmation before dependent tickets claim acceptance. This document defines behavior for SNX-26–SNX-33, SNX-48, SNX-53, and the small Phase 1 status/date correction requested on October 19. It does not claim those features are implemented.

## Data ownership and grain

| Dataset | One row means | Stable key | Owner | Rebuildable? |
|---|---|---|---|---|
| `app.clinics` | One staff-recognized clinic lead | Internal `clinic_id` | Application | No |
| `app.import_batches` / `app.import_rows` | One upload / one attempted sheet row | `batch_id` / `(batch_id,sheet_name,row_number)` | Import service | No |
| `bronze.raw_messages` | One source message, whether linked or not | `(source_channel,source_account_id,source_message_id)` | Connector | No; append-only |
| `app.clinic_source_identities` | One staff confirmation or revocation of a channel participant to a clinic | `mapping_id`; one active mapping per complete source key | Staff workflow | No |
| `app.message_resolutions` | Current clinic association for one raw message | `raw_message_id` | Resolution workflow | No; audit changes |
| `silver.interactions` | One normalized raw message | `raw_message_id` | dbt | Yes |
| `silver.leads` | One clinic, including one with zero messages | `clinic_id` | dbt | Yes |

The application tables hold operational decisions. dbt reads them and the bronze messages; it never writes back to them. The authenticated API may read `app.clinics` for a just-created or corrected row before silver refresh, using the same field precedence as silver. A failed dbt run keeps the previous published silver snapshot and exposes its last successful publication time; it must not present an empty dashboard as fresh data.

## Message envelope and replay

An accepted connector record has `source_channel` (`gmail` or `facebook`), `source_account_id`, `source_message_id`, nullable `source_thread_id`, `direction` (`inbound` or `outbound`), original sender/recipient identifiers, nullable `external_participant_id`, nullable `source_event_at`, `ingested_at`, and unmodified raw payload bytes. Times are UTC instants with offsets at the API boundary. `source_event_at` is what the provider reported; `ingested_at` is when SolNexus durably stored it. A missing or untrustworthy provider time stays null; it is never replaced with ingestion time without a distinct effective-time field. A connector must document stable source IDs. Records without a stable message ID are quarantined with a reason rather than assigned a positional ID.

The uniqueness key is scoped by channel **and connected account**. On retry, an identical message is acknowledged without a second bronze or silver row. If the same key arrives with different payload bytes, preserve the first evidence and record a discrepancy for review. Commit the connector cursor/checkpoint only after the complete page is durable. Thread IDs group messages; they are not message IDs or clinic IDs.

Message-to-clinic association follows [the identity contract](phase1-identity-v1.md): a staff-confirmed exact `(channel, source account, external participant)` mapping is required, and conflicting evidence still sends the message to review. On confirmation or correction, re-evaluate prior messages for **that exact source key** in a bounded, auditable job; leave messages with conflicting evidence unlinked. Record actor, timestamp, old/new `clinic_id`, and reason for every resolution change. A name, phone, or workbook email may suggest a candidate, but cannot create a link or merge clinics automatically. Imported and manual clinics use the same linking process.

## Workbook migration (FR-02)

The private workbook is initial clinic/lead data, not conversation history. **“Ljs Calling Sheet” and “Jacks Calling Sheet” are equally authoritative migration inputs.** They require separate adapters because their layouts differ; worksheet order does not confer priority. After migration, SolNexus is the operational source of truth. Jacks has headers at `A1` Facility, `B1` Name, `C1` Email, `D1` Status, `H1` Status, `I1` Next Step, `J1` Contact, and `K1` Point Person. **The Jacks `D1` header is mistaken:** its values are contact numbers; `H` is the real status column. Its adapter must validate the observed header layout while applying this corrected positional meaning. Ljs has no header row; the first row is data, so its adapter must start at row 1. **No real workbook row values belong in this contract, fixtures, logs, or Jira.**

| Ljs position | Target | Decision |
|---|---|---|
| `A` | `region` | Confirmed October 19. |
| `B` | `province` | Confirmed October 19. |
| `C` | `clinic_name` | Confirmed required clinic/facility field. |
| `D` | `contact_number` | Confirmed text field; retain leading zeroes. |
| `E` | `email` | Confirmed; validate syntax if present. |
| `F` | `address` | Confirmed; do not use alone as identity. |
| `G` | `municipality` | Confirmed; do not use alone as identity. |
| `H` | `calling_notes` | Confirmed October 19: LJ's notes. Preserve as optional text; do not parse it into status, clinic name, or next-action date. |
| `I` | `person_spoken_to` | Confirmed October 19: person Sir LJ spoke to. Preserve separately from the clinic name; it may initialize `contact_person` only when that field is empty and the row is accepted. |

Stage and validate rows from both sheets before resolving clinic records. When staff has confirmed that two rows refer to the same clinic, fields supplied by only one sheet may fill a blank and equal values may be accepted once. Different nonblank values for the same field are a **field conflict**: retain both source values and row references in a durable, access-controlled review record, and do not choose by sheet name or processing order. Keep an existing app value unchanged; for a new clinic, leave a conflicting optional field unset until staff resolves it. If the required clinic name conflicts, hold the proposed clinic in review rather than creating a partly identified record. A possible duplicate whose identity is not confirmed stays `needs_review` and is not merged or separately created until staff resolves the ambiguity. Record the resolving staff member, time, selected or corrected value, and reason. An identical-file replay reuses that decision; a changed workbook requires fresh review for changed or uncertain matches because the sheets have no stable row IDs. This makes the result independent of worksheet order. Re-imports never overwrite later app edits.

| Jacks source column | Proposed target | Rule |
|---|---|---|
| `A` Facility | `clinic_name` | Trim; required nonblank. Preserve original spelling in restricted import evidence. |
| `B` Name | Candidate `contact_person` | Hold authoritative mapping until its meaning is confirmed. |
| `C` Email | `email` | Optional; validate syntax if present; never use alone as clinic identity. |
| `D` mislabeled Status | `contact_number` | Confirmed contact number despite the header. Preserve as text, including leading zeroes; never treat as status. |
| `H` Status | `status_code` | Confirmed status source. Normalize only values with an approved mapping to the Phase 1 enum; otherwise leave current status null and flag the row for review. |
| `I` Next Step | `next_step` | Optional text. Do not invent `next_action_date` by parsing prose. |
| `J` Contact | No automatic mapping yet | Its meaning relative to confirmed phone column `D` needs staff confirmation. |
| `K` Point Person | No automatic mapping yet | Confirm whether this is SolTech owner or clinic contact before mapping. |

Use two explicitly versioned adapters: positional Ljs and header-checked Jacks. The Ljs adapter must not skip row 1 as a header. Unknown sheets or changed Jacks headers fail with a clear format error; blank rows are skipped and counted separately. No partial clinic write occurs for an invalid row. Report **clinic counts** (`created_clinics`) separately from **row counts** (`accepted_rows`, `needs_review_rows`, `rejected_rows`, `skipped_rows`); each attempted row has `accepted`, `needs_review`, `rejected`, or `skipped` plus a sheet/row reference and safe error code. Two accepted rows can contribute to one new clinic. A batch state of `needs_review` can reflect an unresolved field conflict even when `needs_review_rows` is zero. Do not echo private cell contents into routine error responses or logs. An upload can have valid and invalid rows; commit accepted rows and the result ledger atomically per bounded batch, with a resumable batch state on interruption.

[The synthetic two-sheet workbook](fixtures/synthetic-lead-import-v1.xlsx) exercises headerless Ljs row 1, Jacks's misleading `D1` header, valid rows, missing-facility rows, and conflicting phone values. [Its generator](fixtures/build_synthetic_workbook.py) contains only invented values and requires no third-party package. It is a contract fixture; SNX-28 still needs importer tests against the real parser.

An identical file hash is a replay hint. Its prior completed batch may be returned unchanged. A row fingerprint scoped to the adapter version, normalized fields, sheet, and row position helps retry detection. Neither hash proves clinic identity. For a changed file or edited row, match only against an existing recorded import-to-clinic link or an explicit staff decision; ambiguous clinic candidates enter review. A matched re-import never overwrites current application fields. Missing rows in a later workbook never delete clinics. Preserve the originating batch/row and any staff match decision. An exported current lead list has a different format/version marker and must not be silently accepted as the legacy import format.

Candidate discovery must surface exact normalized-name collisions, shared nonblank contact identifiers, and plausible differently written names for staff review across both sheets and existing app clinics. These are **review candidates**, never automatic identity decisions. SNX-28 must document and test its candidate lookup, and staff must reconcile remaining rows before a production migration is accepted. The exact lookup algorithm and thresholds need validation on synthetic cases and a permitted client review; no threshold is approved by SNX-20 yet.

Proposed operational limits: authenticated upload, `.xlsx` only, 10 MiB file and 10,000 populated rows, single active batch per upload, with a documented operator retry path. These limits are capacity assumptions to validate in SNX-28, not facts about the client workbook. Retain only the minimum normalized values and validation metadata needed for reconciliation, with restricted access and a retention period approved before production import.

## Clinic field precedence and status

Clinic name/contact/status/next action are operational fields. Explicit staff corrections take precedence over imported values. Accepted import values initialize fields once; re-imports do not overwrite them. Rule-based parsing of messages may populate **suggestions** in silver interactions but may not silently mutate `app.clinics`. Null means unknown; an explicit staff clear must remain clear and must not be refilled from an old import or parser output. Store field-level edit provenance or an equivalent audit event with actor, time, old/new value, and reason. Concurrency control uses `version` or `updated_at` preconditions and returns a conflict if another staff member edited the clinic first.

Proposed Phase 1 status codes are `contacted`, `proposal_sent`, `awaiting_demo`, `follow_up_needed`, and `closed`; null is unknown. The list follows the requirement and dashboard examples and does **not** add `demo_booked`. Closed clinics are excluded from the due view even if an old next-action date remains in the record; any won/lost outcome is future metadata, not an assumed Phase 1 status. Workbook values not confidently mappable to this set remain unmapped and require review. `next_action_date` is an ISO date in the `Asia/Manila` business calendar, independent of message UTC timestamps.

No workbook column has yet been confirmed as a next-action date. Imported clinics with null `next_action_date` remain visible in All clinics and are excluded from Due today. Before Phase 1 acceptance, confirm a date mapping from the remaining workbook fields or demonstrate staff entering dates through the Phase 1 correction action; otherwise the imported due-list workflow is incomplete.

The approved basic Phase 1 correction action updates `status_code` and/or `next_action_date` for an existing clinic, with staff actor and audit trail. It does not create a call or conversation record. Manual call logging, snooze, and collapse preferences remain separate scope decisions. SNX-20 should add a delivery ticket or amend the deferred SNX-49 ticket and Phase 1 gate after the team approves the scope change; the contract alone does not deliver UI/API behavior.

## Dashboard and export semantics

The landing page shows **Due today** above **All clinics** as two visible tables. Due includes non-closed clinics with `next_action_date <=` the current `Asia/Manila` date, including overdue rows; null dates and closed clinics are excluded. Sort by earliest next-action date, then oldest known last-contact instant (null last), then casefolded clinic name, then `clinic_id`. All clinics includes imported and manually created clinics even with no messages. A single-select status filter and case-insensitive clinic/contact search apply to All clinics; the default is unfiltered. Search/filter must not hide Due today on initial load. The due rule and UI are proposed defaults pending client/team approval, as the wireframe contains controls that are not all in Phase 1 scope.

`last_contact_at` derives only from a linked interaction with a trustworthy source event time; if absent, show null. This avoids treating import time or sync time as a conversation. History orders by event time then source key, includes only linked interactions for that clinic, and labels derived topic/status as suggestions. Unlinked messages remain in authorized review, not another clinic's history.

FR-19 export is a current **snapshot** of authorized clinic data, not a backup or import source. Proposed columns: `clinic_id`, `clinic_name`, `contact_person`, `contact_number`, `email`, `region`, `province`, `municipality`, `address`, `status_code`, `next_action_date`, `next_step`, `point_person`, `discovery_source`, `last_contact_at`, `origin`. Include a format/version marker and export time; no raw message payload, private import errors, or unlinked messages. Escape spreadsheet formula-leading text on export. Export and list must reflect the same effective field values for a given snapshot.

## API shape (proposed `/api/v1`)

All endpoints require the authenticated SolTech staff session except login. Use JSON errors `{ "error": { "code": "...", "message": "...", "details": [] } }`; omit private row content. `401` means no valid session, `403` means insufficient permission, `409` means concurrent edit or unresolved identity conflict, `422` means field validation failure, and `503` means temporarily unavailable data. Never return a success response while showing stale data as fresh.

| Method/path | Request | Success |
|---|---|---|
| `POST /api/v1/auth/login` | Email/password over HTTPS | `200` session cookie (HttpOnly, Secure, SameSite) plus staff summary; invalid credentials `401` |
| `POST /api/v1/auth/logout` | Session | `204`; invalidate server session |
| `POST /api/v1/clinics` | Required `clinic_name`; optional FR-20 contact/status/date/discovery fields | `201` clinic with stable `clinic_id` and `version` |
| `PATCH /api/v1/clinics/{clinic_id}` | `status_code` and/or `next_action_date`, plus `version` | `200` updated clinic; stale version `409` |
| `POST /api/v1/imports` | Multipart `.xlsx` legacy workbook | `202` batch ID/state; poll result endpoint |
| `GET /api/v1/imports/{batch_id}` | Batch ID | `200` counts and row results with safe codes |
| `GET /api/v1/leads` | `status`, `q`, `limit`, `cursor` | `200` All clinics page and publication metadata |
| `GET /api/v1/leads/due` | Optional business date for test/operator use; ordinary users get today | `200` due rows and publication metadata |
| `GET /api/v1/leads/{clinic_id}/history` | `limit`, `cursor` | `200` linked interactions ordered by event time |
| `GET /api/v1/messages/review` | `reason`, `limit`, `cursor` | `200` unresolved messages with candidate evidence for authorized staff |
| `POST /api/v1/source-identities/confirm` | Exact source identity key, `clinic_id`, nullable `expected_active_mapping_id`, reason | `200` recorded confirmation and bounded re-evaluation job ID; conflicting active mapping `409` |
| `GET /api/v1/leads/export` | No body | `200` spreadsheet with format/version marker and snapshot time |

Pagination uses an opaque cursor with stable tie-break keys and an upper bound (proposed 100 per page); invalid cursors return `422`. `published_at` denotes the last successful silver publication, not the latest connector poll. `as_of` is the response time. A newly created clinic may be read through from `app.clinics` before publication, with `pending_projection: true` so freshness is honest. The exact API examples are in [phase1-api-examples-v1.json](fixtures/phase1-api-examples-v1.json); payloads use synthetic data.

## Phase 2 boundaries

Viber adds a provider adapter to the same envelope only after access and conversation coverage are proven. LLM output is versioned enrichment or a suggestion; it cannot overwrite staff state without a separate approval rule. S3 is optional raw retention, not a replacement for the Phase 1 database contract.

Proposed gold metric grain is **one clinic in a defined cohort**, with append-only status-transition events as evidence. For each stage (`contacted`, `proposal_sent`, `awaiting_demo`, `closed`), a funnel count is the number of distinct cohort clinics whose first confirmed transition to that stage occurred by the report cutoff; a stage rate divides that count by the cohort size, with zero denominator reported as null. The cohort rule (creation period versus first contact period), whether stages may be skipped, and whether `closed` means won are **unapproved**. Do not infer a conversion rate from the current status snapshot alone.

Proposed response-time grain is one eligible inbound message. Pair it to the first later outbound message for the same confirmed clinic and source identity, before the next inbound message; `response_seconds = outbound.source_event_at - inbound.source_event_at`. Exclude messages with missing/untrustworthy event time from the duration calculation and report them separately; unanswered messages remain in a separate count, not zero seconds. The pairing window, business-hours adjustment, and whether staff calls count as responses need approval. Until these rules and complete histories are approved, do not publish a number that implies a measured conversion or response rate. Airflow alerts and a dashboard freshness threshold are separate Phase 2 contracts.

## Approval gates and handoff

1. Both workbook sheets are equally authoritative migration inputs; Ljs `A`–`I` mapping is confirmed, with H as notes and I as person spoken to. Cross-sheet conflicts require staff review, with no sheet taking priority. Jacks `D` is confirmed phone despite its header, and `H` is confirmed status. SolTech/team still needs to define the values-to-enum mapping for Jacks `H`, Jacks `B`/`J`/`K`, and any actual date field. SNX-28 also needs a reviewed candidate lookup for differently written rows. Until then, the importer can map confirmed columns and show a preview, but cannot claim complete status/date or deduplication coverage.
2. SolTech/team approves the proposed status vocabulary, due/overdue and closed rules, Manila business date, filter behavior, refresh expectation, upload limits, export columns, and retention period.
3. Team records Phase 1 capacity and updates the backlog/acceptance gate for basic status/date correction. Call logging remains separately decided.
4. SNX-26 implements durable schema/migrations; SNX-28 implements the adapter; SNX-29 owns silver models; SNX-30 owns read APIs; SNX-48/53 own create/export. Each ticket validates against synthetic examples and records any contract revision.

These are explicit gates, not evidence of client approval or implementation completion.
