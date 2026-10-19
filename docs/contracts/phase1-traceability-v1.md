# SNX-20 requirement and decision traceability — proposed v1

Status: **draft for team review, October 19, 2026**. This maps requirements to the contract that defines behavior and the ticket that implements it. The contract is not implementation evidence. Phase 1 is the semester minimum; Phase 2 begins only after Phase 1 acceptance and available capacity/access.

| Requirement or behavior | Contract decision/evidence | Implementation owner | Open gate |
|---|---|---|---|
| FR-01 Gmail ingestion; FR-03 bronze messages; NFR-09 lineage | [Data/API contract](phase1-data-api-v1.md): source scoped message key, raw payload, event and ingest timestamps, replay | SNX-21 spike, SNX-26 schema, SNX-32 connector | Real synthetic API access and stable ID evidence |
| FR-11 Facebook ingestion | Same envelope and staff-confirmed [identity contract](phase1-identity-v1.md) | SNX-22 spike, SNX-36 connector | Real synthetic Page API evidence |
| FR-02 legacy workbook; NFR-01 deduplication | [Data/API contract](phase1-data-api-v1.md) and [synthetic two-sheet workbook](fixtures/synthetic-lead-import-v1.xlsx): equal migration authority, confirmed Ljs A–I (H notes, I person spoken to) and Jacks D/H meanings, staff review of cross-sheet conflicts, row ledger, retry protection | SNX-20 mapping decision, SNX-28 import, SNX-26 schema | Jacks H value normalization and B/J/K meanings; retention approval |
| FR-04 silver leads/interactions; NFR-06 maintainability | [ERD draft](phase1-erd-schema-draft.md): operational state is durable; dbt projections are rebuildable | SNX-26 schema, SNX-29 dbt | Final schema and parser/status approval |
| FR-05 scheduling; NFR-02/NFR-08 reliability | Last successful publication, checkpoint-after-write, retry semantics in data/API contract | SNX-33 Airflow | Schedule and freshness expectation |
| FR-06 API; FR-07 Due; FR-08 All/history; FR-09 filtering | [Data/API contract](phase1-data-api-v1.md), [synthetic examples](fixtures/phase1-api-examples-v1.json), and [editable wireframe 02](../wireframes/02-dashboard-editable.html): explicit unknown clinic name, visible email action, versioned row edits | SNX-26 inquiry schema, SNX-30 API, SNX-31 dashboard | Due/overdue, timezone, filter and sort approval; confirmed workbook date mapping or demonstrated staff date entry for imported due leads; confirmation evidence UI review |
| FR-10 and NFR-03 staff access | Auth and errors in data/API contract | SNX-27 auth, SNX-30 API, SNX-31 UI | Session policy and production privacy review |
| FR-19 current lead export | Snapshot columns/marker and authorization in data/API contract | SNX-53 export | Column approval and formula escaping |
| FR-20 manual clinic creation | Stable clinic ID, nullable fields, API example, source identity confirmation | SNX-48 create UI/API, SNX-26 schema | Form/status vocabulary approval |
| Spreadsheet-style dashboard row correction | Requested October 19; versioned edits, audit, unknown-name inquiry, and clinic confirmation flow in data/API contract | **Backlog amendment needed**: SNX-26 schema, SNX-30 API, SNX-31 dashboard, SNX-48 editor scope | Team capacity and acceptance gate update |
| Manual call log, snooze, collapse | Separate product choices; wireframes alone do not approve them | SNX-49 remainder, SNX-50 or later | Client/team decision |

## Required review evidence

- Review the contract and synthetic examples with the two lead-tracking users; record accepted defaults and unresolved fields. A reviewer name, date, and decision record are required before marking SNX-20 done.
- Record actual team capacity before adding the expanded row editor and inquiry workflow to the Phase 1 commitment. The request establishes desired scope; it does not demonstrate capacity.
- Keep provider access state separate from fixture success. A fixture validates mapping behavior but cannot prove Gmail or Facebook API access.
- Verify imported clinics with no confirmed next-action date appear in All leads and remain out of Due today; record the staff date-entry or approved source mapping that makes imported follow-ups actionable. Verify initial-message inquiries show **Clinic name unknown** and an email action before staff confirms a reply.
- Do not mark SNX-20 or dependent tickets complete merely because these documents exist. SNX-20 acceptance specifically requires review, field decisions, and approved contracts.

## Phase 2 interface notes

FR-12 Viber uses the same source envelope after a GO decision on bot access and coverage (SNX-23/37). FR-13 LLM enrichment is versioned suggestion data (SNX-24/38). FR-14 S3 archives raw payloads with replay/reconciliation (SNX-39). FR-15 gold funnel and response metrics require status events and agreed denominators/pairing windows (SNX-40/41). FR-18 alerts and freshness thresholds are SNX-42. FR-16 finance and FR-17 digest remain stretch goals. None of these substitute for incomplete Phase 1 evidence.
