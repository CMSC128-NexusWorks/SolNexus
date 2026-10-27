# SNX-20 requirement and decision traceability — proposed v1

Status: **draft for team review, October 19, 2026**. This maps requirements to the contract that defines behavior and the ticket that implements it. The contract is not implementation evidence. Phase 1 is the semester minimum; Phase 2 begins only after Phase 1 acceptance and available capacity/access.

| Requirement or behavior | Contract decision/evidence | Implementation owner | Open gate |
|---|---|---|---|
| FR-01 Gmail ingestion; FR-03 bronze messages; NFR-09 lineage | [Data/API contract](phase1-data-api-v1.md): source scoped message key, raw payload, event and ingest timestamps, replay; [SNX-21 evidence](../spikes/SNX-21-gmail-oauth-findings.md) records real synthetic reads, refresh and repeatable IDs | SNX-21 spike, SNX-26 schema, SNX-32 connector | Spike GO recorded October 26; peer review/integration pending. Durable ingestion, replay protection and integrated FR-01 acceptance remain open. |
| FR-02 legacy workbook; NFR-01 deduplication | [Data/API contract](phase1-data-api-v1.md) and [synthetic two-sheet workbook](fixtures/synthetic-lead-import-v1.xlsx): equal migration authority, confirmed Ljs A–I (H notes, I person spoken to) and Jacks D/H meanings, staff review of cross-sheet conflicts, row ledger, retry protection | SNX-20 mapping decision, SNX-28 import, SNX-26 schema | Jacks H value normalization and B/J/K meanings; retention approval |
| FR-04 silver leads/interactions; NFR-06 maintainability | [ERD draft](phase1-erd-schema-draft.md): operational state and append-only status evidence are durable; dbt projections are rebuildable. Imported status is a baseline, not a dated conversion event | SNX-26 schema, SNX-29 dbt | Final schema and status vocabulary approval |
| Message association after staff confirmation, correction or revocation | [Identity contract](phase1-identity-v1.md) requires bounded re-evaluation for the exact source key, change audit and current-link checks on history reads; [synthetic lifecycle cases](fixtures/identity-resolution-v1.json) cover confirmation, correction and revocation | SNX-26 resolution tables/job, SNX-29 projection, SNX-30 history API | Implement and verify retries, conflict review and stale-link removal |
| FR-05 scheduling; NFR-02/NFR-08 reliability | Last successful publication, checkpoint-after-write, retry semantics and an hourly refresh proposal in data/API contract | SNX-33 Airflow | Approve interval/freshness threshold and validate provider quotas |
| FR-06 API; FR-07 Due; FR-08 All/history; FR-09 filtering; FR-21 editable rows | [Data/API contract](phase1-data-api-v1.md) and [synthetic examples](fixtures/phase1-api-examples-v1.json) specify explicit unknown clinic name, visible email action and versioned row edits; [static wireframe 02](../wireframes/02%20%C2%B7%20Dashboard%20%E2%80%94%20default%20view%20%28FR-07%20%2B%20FR-08%29.png) provides the original dashboard layout only | SNX-26 inquiry schema, SNX-29 silver, SNX-30 API, SNX-31 dashboard | Due/overdue, timezone, filter and sort approval; confirmed workbook date mapping or demonstrated staff date entry for imported due leads; confirmation evidence UI review |
| FR-10 and NFR-03 staff access | Auth and errors in data/API contract | SNX-27 auth, SNX-30 API, SNX-31 UI | Session policy and production privacy review |
| FR-19 current lead export | Snapshot columns/marker and authorization in data/API contract | SNX-53 export | Column approval and formula escaping |
| FR-20 manual clinic creation | Stable clinic ID, nullable fields, API example, source identity confirmation | SNX-48 create UI/API, SNX-26 schema | Form/status vocabulary approval |
| FR-21 spreadsheet-style dashboard row correction | Versioned edits, audit, unknown-name inquiry, and clinic confirmation flow in data/API contract | SNX-26 schema, SNX-29 projection, SNX-30 API, SNX-31 dashboard, SNX-43 acceptance | Team capacity and acceptance gate review |
| Manual call log, snooze, collapse | Separate product choices; wireframes alone do not approve them | SNX-49 remainder, SNX-50 or later | Client/team decision |

## Required review evidence

- Review the contract and synthetic examples with the two lead-tracking users; record accepted defaults and unresolved fields. A reviewer name, date, and decision record are required before marking SNX-20 done.
- Record actual team capacity and reforecast delivery of FR-21's row editor and inquiry workflow against the Phase 1 gate. The requirement establishes desired scope; it does not demonstrate capacity.
- Keep provider access state separate from fixture success. A fixture validates mapping behavior but cannot prove Gmail API access for Phase 1 or Facebook API access for Phase 2.
- Verify imported clinics with no confirmed next-action date appear in All leads and remain out of Due today; record the staff date-entry or approved source mapping that makes imported follow-ups actionable. Verify initial-message inquiries show **Clinic name unknown** and an email action before staff confirms a reply.
- Do not mark SNX-20 or dependent tickets complete merely because these documents exist. SNX-20 acceptance specifically requires review, field decisions, and approved contracts.

## Decision status for SNX-20

The exact source-identity rule and its historical re-evaluation lifecycle are specified in the identity contract. The data/API and ERD files provide implementable proposals, not a record of client or team approval. The following decisions still require named reviewers and a dated outcome before SNX-20 can be closed:

| Decision | Safe interim behavior | Approval or evidence needed |
|---|---|---|
| Jacks `B`/`J`/`K`, status values and date source | Preserve uncertain values only as restricted import evidence. Accept Jacks `H` only on exact approved status label/code; otherwise require review. Do not infer a date from prose; staff may enter it in FR-21 | Staff confirms column meanings and status mapping; either confirms a date source or demonstrates staff date entry |
| Due/status/filter, refresh and export rules | Use the proposed Manila date, due/overdue sorting, enum, hourly connector polling, visible freshness timestamp and export column list only as reviewable defaults | Two lead-tracking users approve or revise defaults; SNX-33 validates provider quotas and refresh interval |
| Import sizing, candidate discovery and retention | Keep candidate matches review-only; use proposed size limits in tests, with no production import of private rows | SNX-28 validates candidate lookup and workbook limits; client/team approves retention period |
| FR-21 delivery capacity | Keep editable rows and unknown-name inquiry in the Phase 1 backlog; do not mark delivery complete | Team records available capacity and reviews the November 20 gate |
| Review and publication | Keep draft/proposed labels and Jira scope items unchecked | Record reviewer names, date, decisions and versioned approval in SNX-20 |

## Phase 2 interface notes

FR-11 Facebook uses the same source envelope after a GO decision on Page access and review path (SNX-22/36). FR-12 Viber uses the same source envelope after a GO decision on bot access and coverage (SNX-23/37). FR-13 LLM enrichment is versioned suggestion data (SNX-24/38). FR-14 S3 archives raw payloads with replay/reconciliation (SNX-39). FR-15 gold funnel and response metrics require status events and agreed denominators/pairing windows (SNX-40/41). FR-18 alerts and freshness thresholds are SNX-42. FR-16 finance and FR-17 digest remain stretch goals. None of these substitute for incomplete Phase 1 evidence.
