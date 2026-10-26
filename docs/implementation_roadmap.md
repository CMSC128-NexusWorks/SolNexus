# SolNexus delivery roadmap and Jira backlog

Planning revision: October 25, 2026 (Asia/Manila). Jira project: **SNX — CMSC 128/129**. Original backlog planning record: [SNX-15](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-15). [Machine-readable issue plan](jira_backlog_plan.json).

SNX-15 now records this revision. It remains In Review pending team capacity review. Five earlier Phase 2 Blocks links to the Phase 1 gate were removed. The SNX-36 → SNX-43 link still awaits deletion in Jira.

## Delivery decision

**Phase 1 is this semester’s minimum finished product.** Complete and verify it before starting Phase 2 implementation. Phase 2 is an aspiration for remaining time and provider access; incomplete Phase 2 work is reported separately. FR-16 finance and FR-17 digest remain stretch goals. Sprint labels are planning labels; the connected Jira tool does not expose native board sprint assignment.

Phase 1 includes Gmail API conversation ingestion; import of clinic/lead rows from both equally authoritative sheets of the private `leads-data/Leads Spreadsheet.xlsx` format; download of the current lead list; manual Add clinic (wireframe 06); and FR-21 spreadsheet-like editing of operational rows in the Due today, Needs clinic name and All leads dashboard views (wireframe 02). Authorized staff can edit contact details, status, next-action date, notes, person spoken to and confirmed clinic fields with save/cancel, validation, audit and stale-edit protection. New inquiries display **Clinic name unknown** and an **Email to ask** action until staff review the lead's reply and confirm the clinic name. Raw-message bronze storage, dbt silver processing, Airflow retries and authenticated FastAPI support these workflows. The lead workbook contains operational lead data, **not** Facebook or Viber conversation exports. Do not place its real rows in fixtures, Jira descriptions, or logs.

Phase 2 adds Facebook Page conversations after an access and review-path decision and supported Viber bot conversations after an access and workflow-coverage decision, LLM enrichment, private S3 raw retention, gold conversion/response analytics and pipeline failure alerts. The [Viber REST API](https://developers.viber.com/docs/api/rest-bot-api/) documents commercial bot access and webhook callbacks; it does not establish access to the client’s existing personal conversation history. A GO decision requires evidence for the intended conversation workflow.

## Acceptance sequence

| Gate | Target | Required evidence |
|---|---|---|
| First integrated slice | Sprint 2, October 30 | [SNX-35](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-35): synthetic two-sheet lead import plus Gmail/fixture through the authenticated dashboard; record gaps. |
| Phase 1 semester minimum | Sprint 3, November 20 | [SNX-43](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-43): real synthetic Gmail API runs; two-sheet spreadsheet upload and current-list download; Add clinic and FR-21 editable dashboard rows with clinic-name confirmation; core data, API and UI checks. Capacity review remains open. |
| Release stabilization | Sprint 4, November 27–December 4 | [SNX-44](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-44), [SNX-46](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-46), [SNX-47](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-47): regression, access, recovery, deployment and demo evidence. |
| Phase 2 extension | After Phase 1 acceptance, if time and access permit | Separate evidence for each Phase 2 FR; no mock or lead-sheet row stands in for a live Viber/LLM/S3 integration. |

The original two-phase-by-November-20 gate was replaced by the Phase 1 minimum. November 20 remains the release candidate checkpoint; Sprint 4 is for stabilization. A missed Phase 1 requirement is reported as incomplete rather than silently reclassified as Phase 2.

## Jira categories and priorities

Priority labels map to Jira native priorities: P0 Highest, P1 High, P2 Medium, P3 Low. Primary categories are title prefixes and labels; they identify the work’s main responsibility, even when an issue crosses UI, API and data layers. In particular, spreadsheet import, LLM-to-silver enrichment, pipeline alerting and finance ingestion are DATA work, while login and read APIs remain BACKEND. The Phase 1 epic is CORE because it spans the stack.

### Phase 1 minimum

| Issue | Work | Category | Priority | Target |
|---|---|---|---|---|
| [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) | Resolve scope gaps and publish data/API contracts | DOCS | P0 | Sprint 2 |
| [SNX-21](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-21) | Spike: prove Gmail OAuth and synthetic mailbox ingestion | INTEGRATION | P0 | Sprint 2 |
| [SNX-25](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-25) | Validate shared test hosting for Phase 1 | DEVOPS | P0 | Sprint 2 |
| [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26) | Implement bronze schema, lead identity mapping and repeatable migrations | DATA | P0 | Sprint 2 |
| [SNX-27](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-27) | Implement two-user login and protect application APIs | BACKEND | P0 | Sprint 2 |
| [SNX-28](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-28) | Import existing SolTech lead spreadsheet records | DATA | P0 | Sprint 2 |
| [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29) | Build dbt silver leads and interactions with baseline status parsing | DATA | P0 | Sprint 2 |
| [SNX-30](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-30) | Expose authenticated lead/history queries and version-checked operational row updates | BACKEND | P0 | Sprint 2 |
| [SNX-31](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-31) | Deliver Due today, Needs clinic name and All leads views with FR-21 editable rows and clinic-name confirmation | FRONTEND | P0 | Sprint 2 |
| [SNX-32](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-32) | Implement incremental Gmail ingestion with replay protection | INTEGRATION | P0 | Sprint 2 |
| [SNX-33](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-33) | Orchestrate Gmail and bronze-to-silver runs in Airflow | DATA | P0 | Sprint 2 |
| [SNX-34](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-34) | Add reproducible checks and a shared test deployment | DEVOPS | P0 | Sprint 2 |
| [SNX-35](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-35) | Verify the first Phase 1 core slice and Sprint 2 exit | QA | P0 | Sprint 2 |
| [SNX-43](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-43) | Verify Phase 1 acceptance and report Phase 2 readiness | QA | P0 | Sprint 3 |
| [SNX-48](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-48) | Add named clinic lead manually | FRONTEND | P0 | Sprint 3 |
| [SNX-53](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-53) | Download current lead data as a spreadsheet | DATA | P0 | Sprint 3 |

### Release stabilization

| Issue | Work | Category | Priority | Target |
|---|---|---|---|---|
| [SNX-44](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-44) | Run frozen-release regression and verify critical defect fixes | QA | P0 | Sprint 4 |
| [SNX-45](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-45) | Verify keyboard access, responsive tables and UI error recovery | QA | P1 | Sprint 4 |
| [SNX-46](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-46) | Verify access controls, recovery and performance of the frozen build | QA | P0 | Sprint 4 |
| [SNX-47](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-47) | Verify deployment and finalize the release runbook and demo | DOCS | P0 | Sprint 4 |

### Phase 2, conditional after Phase 1

| Issue | Work | Category | Priority | Target |
|---|---|---|---|---|
| [SNX-22](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-22) | Spike: prove Facebook Page conversation access and review path | INTEGRATION | P1 | After Phase 1 |
| [SNX-36](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-36) | Ingest synthetic Facebook Page conversations automatically | INTEGRATION | P1 | After Phase 1 |
| [SNX-23](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-23) | Spike: validate Viber bot access against the client's conversation workflow | INTEGRATION | P1 | After Phase 1 |
| [SNX-24](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-24) | Spike: select and evaluate structured LLM extraction | INTEGRATION | P1 | After Phase 1 |
| [SNX-37](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-37) | Ingest synthetic Viber bot messages through verified callbacks | INTEGRATION | P1 | After Phase 1 |
| [SNX-38](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-38) | Integrate validated LLM enrichment into the silver pipeline | DATA | P1 | After Phase 1 |
| [SNX-39](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-39) | Archive raw conversations to private S3 with replay and reconciliation | DATA | P1 | After Phase 1 |
| [SNX-40](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-40) | Build gold conversion and response metrics with authenticated APIs | DATA | P1 | After Phase 1 |
| [SNX-41](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-41) | Show conversion and response metrics in a minimal analytics view | FRONTEND | P1 | After Phase 1 |
| [SNX-42](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-42) | Notify failed pipeline runs and surface last successful sync | DATA | P1 | After Phase 1 |

### Stretch and deferred

| Issue | Work | Category | Priority | Target |
|---|---|---|---|---|
| [SNX-49](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-49) | Decision-gated: log calls and in-person interactions | BACKEND | P2 | After Phase 1 |
| [SNX-50](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-50) | Decision-gated: persist dashboard table collapse preferences | FRONTEND | P3 | After Phase 1 |
| [SNX-51](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-51) | Deferred: add the optional AWS cost reporting workflow | DATA | P3 | After Phase 1 |
| [SNX-52](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-52) | Deferred: send the optional daily follow-up digest | BACKEND | P3 | After Phase 1 |

## Requirements and dependency notes

- [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) defines the private workbook’s field mapping, duplicate/update precedence, manual clinic identity, conversation association, export columns and API contracts. Its agreed staff-confirmed message association rule is in [the Phase 1 identity contract](contracts/phase1-identity-v1.md); the [data/API proposal](contracts/phase1-data-api-v1.md) and [traceability review](contracts/phase1-traceability-v1.md) record remaining decisions. Both workbook sheets are equal migration inputs, with separate adapters and staff review of conflicting values. LJ's H/I columns are notes/person spoken to. FR-21's proposed row editor and unknown-clinic inquiry flow extend the [static dashboard wireframe 02](wireframes/02%20%C2%B7%20Dashboard%20%E2%80%94%20default%20view%20%28FR-07%20%2B%20FR-08%29.png) and are specified in the data/API proposal; delivery capacity still needs review. Call logging remains deferred. No candidate-matching algorithm is preselected by this roadmap.
- [SNX-28](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-28) imports lead rows from both sheets. [SNX-53](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-53) downloads current lead rows. [SNX-48](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-48) creates a named clinic without a prior conversation. [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26), [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29), [SNX-30](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-30) and [SNX-31](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-31) carry FR-21's inquiry, persistence, API and row-editor work. Team capacity and acceptance evidence remain open.
- [SNX-22](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-22) and [SNX-36](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-36) begin only after Phase 1 acceptance. They must prove real synthetic Facebook Page ingestion for Phase 2; mocks and lead-sheet rows do not complete FR-11.
- [SNX-23](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-23) and [SNX-37](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-37) are Phase 2 Viber work. Bot access and coverage remain uncertain. FR-12 is not completed by importing the lead workbook.
- [SNX-25](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-25) now covers shared Phase 1 hosting readiness. S3 and alert-provider decisions belong to [SNX-39](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-39) and [SNX-42](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-42) after Phase 1 acceptance.
- Real client lead rows stay private. Development fixtures use synthetic rows shaped like the workbook. Real API access with synthetic conversations is distinct from mocks and from production client access.

## Risks and limits

- **Facebook access:** Page permissions or webhook access may block Phase 2 Facebook delivery. After Phase 1 acceptance, record a GO/NO-GO decision and report FR-11 separately if live synthetic ingestion cannot run.
- **Viber coverage:** the documented bot API may not include existing personal chats. Phase 2 scope is conditional on a workflow test, not an assumption that all historical conversations are available.
- **Lead reconciliation:** imported and manually created clinics must survive dbt rebuilds and avoid false cross-channel merges. SNX-20 defines identity and data ownership before implementation.
- **Capacity:** hours and velocity are unmeasured. Phase 2 has no fixed sprint or due-date commitment until Phase 1 is accepted and the team reforecasts.
- **Jira dependencies:** five earlier obsolete Phase 2 Blocks links to SNX-43 were removed. The planned direct blockers are SNX-35, SNX-48 and SNX-53. Jira still has an obsolete SNX-36 Blocks SNX-43 link because the connected Jira tool cannot delete issue links; remove link ID 10040 before using Jira blockers as the acceptance gate.

This revision updates the plan and issue text. Actual provider access, production data permissions, native sprint assignment and software behavior still require implementation and evidence.
