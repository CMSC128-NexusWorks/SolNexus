# SolNexus Phase 1–2 delivery roadmap and verified Jira backlog

Planning date: October 15, 2026 (Asia/Manila). Repository baseline: `2069280`. Jira project: **SNX — CMSC 128/129**. Planning record: [SNX-15](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-15).

**Outcome:** 37 new issues (4 epics, 23 tasks, 9 stories and 1 subtask), plus the reused planning story, with 55 verified directional Blocks links. All 38 planned issues are unassigned. Application implementation was not performed or runtime-tested during this planning task.

## A. Project analysis

SolNexus centralizes SolTech EMR's clinic lead conversations and replaces fragmented spreadsheet lookup with an immediately visible follow-up list and searchable interaction history. Sources inspected in full: [proposal](project_proposal.md), [requirements](software_requirements.md), [architecture](architecture.md), [all eight wireframes](wireframes/), README and all substantive application/pipeline/deployment source files.

Phase 1 requires Gmail automation, manual Facebook/Viber export uploads, original raw PostgreSQL messages, dbt leads/interactions, scheduled Airflow processing/retries, FastAPI, authenticated two-table React dashboard, history and filtering. Phase 2 adds live Facebook/Viber ingestion, LLM structured extraction, S3 retention, dbt conversion/response analytics and failure alerts. FR-16 finance and FR-17 digest are explicitly stretch goals.

### Existing work to reuse

- Jira SNX-4–8 and SNX-10–14 record completed proposal/interview/requirements/backlog/scaffold/wireframe work. They were not modified.
- SNX-13 is supported by Compose, Dockerfiles, PostgreSQL 16, FastAPI settings and `/health`, React 18/TypeScript/Vite, Airflow 2.10.5 and dbt configuration.
- SNX-14 is supported by eight committed wireframes, including explicit open questions.
- Backend has no business endpoints, database access layer or application authentication. The health endpoint checks configuration presence, not a database query.
- Frontend is a placeholder, not a working dashboard.
- Both DAGs contain no-op tasks and no schedule; dbt model directories contain only placeholders. PostgreSQL initialization creates only Airflow's metadata database.
- No implemented provider adapters, business migrations, silver/gold models, S3/LLM integrations, test suites or CI workflow were found.
- SNX-15 was reused for this planning deliverable. SNX-3 is an unrelated, empty “Subtask 2.1” placeholder; no evidence supports carrying it into development, so it was left untouched.
- Repository was clean at inspection. No scaffold functionality was assumed operational merely because configuration exists.

### Assumptions and decisions requiring clarification

1. The user's academic calendar supersedes the proposal's explicitly provisional two-semester timeline. The functional requirements themselves remain authoritative.
2. The user confirms **none of Gmail, Facebook, Viber, AWS or LLM credentials are ready** and prefers team-controlled test accounts with synthetic conversations. Live API calls against synthetic test data demonstrate integration; they do not establish production client access. No client data is needed for development.
3. Five team members are listed, but hours/availability/velocity are unknown. Sprint commitments remain conditional on capacity review in [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20). Reserve approximately 20% of actual available development capacity for integration/defects; this is a proposed planning policy, not a measured estimate.
4. Missing specifications include CSV formats, precise schema and identity rules, auth/session strategy, statuses, next-action derivation, due/overdue and timezone behavior, API contracts, refresh cadence, analytics definitions, provider/budget choices, retention, workload and performance targets.
5. Proposed defaults awaiting confirmation: stacked tables; simple single-select status filtering plus clinic/contact search; Asia/Manila business day; overdue included; next-action date then oldest-contact ordering. Closed/no-date handling must be explicit.
6. Wireframe 05 explicitly says collapse/persistence is unconfirmed. Wireframe 06 explicitly says manual clinic creation needs a new requirement. Wireframe 07 adds call logging/correction and an unapproved “Demo booked” status. These are decision-gated Future items, not silently added to mandatory scope. This leaves an important product-utility risk for phone-based outreach.
7. No UI specification exists for uploads or Phase 2 analytics. Define minimal layouts within the documented requirements in [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20); no new design system or feature expansion.
8. dbt-owned tables must be separated from any future application-edit overlay. A rebuild must never erase accepted user corrections. Preserve status-event and message-direction data early so real conversion/response metrics can be calculated.

## B. Academic sprint roadmap

| Sprint | Development | Review / retrospective | Objective and completion evidence |
|---|---|---|---|
| Sprint 1, past | Sep 28–Oct 12 | Oct 12–15 | Reuse completed setup and wireframes; carry only missing contracts/readiness into new work. Historical records remain intact. |
| Sprint 2 | Oct 16–30 | Nov 2–5 | Contracts by Oct 19; Gmail access decision Oct 20; Facebook/Viber decisions Oct 21; LLM/AWS/alerts decisions Oct 22. Deliver schema/auth/imports/dbt/API/dashboard and shared test environment. Target imported end-to-end slice Oct 28 and real test Gmail orchestration/Phase 1 evidence Oct 30. |
| Sprint 3 | Nov 9–20 | Nov 23–26 | S3 by Nov 12; access-gated Facebook/Viber, LLM and gold APIs by Nov 13; alerts Nov 16; analytics UI Nov 17. Begin integrated acceptance by Nov 16. All mandatory Phase 1–2 features and release-blocking fixes pass the Nov 20 candidate gate, or explicitly report unmet scope. |
| Sprint 4 | Nov 27–Dec 4 | Dec 7–9 | Strict freeze: regression, UI/accessibility defect repair, security/recovery/performance checks, deployment verification, docs and demo only. Release evidence and rehearsal ready Dec 4; final presentation and member evaluation Dec 10. |

There are **21 weekdays** in Sprint 2 plus Sprint 3 before holidays or other academic commitments (11 + 10), and six weekdays in Sprint 4. The review periods and November 6–8 are not treated as extra feature-development capacity. Sprint 2 has 16 new work items; Sprint 3 has eight; Sprint 4 has three parent tasks plus one QA subtask. These counts are not estimates of effort or staffing.

## C. Prioritized Jira backlog

Native priorities: **P0 = Highest, P1 = High, P2 = Medium, P3 = Low**. Every issue has the requested description, scope checklist, technical considerations, acceptance criteria, dependencies, Definition of Done and planning fields. Complexity is qualitative; no unsupported points or time estimates were assigned.

| Epic | Title | Primary category | Priority | Target | Status |
|---|---|---|---|---|---|
| [SNX-16](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-16) | Deliver the authenticated Phase 1 lead workflow | BACKEND | P0 | Sprints 2–3 | To Do |
| [SNX-17](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-17) | Validate and deliver automated test-channel ingestion | INTEGRATION | P1 | Sprints 2–3 | To Do |
| [SNX-18](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-18) | Deliver validated extraction, S3 retention and gold analytics | DATA | P1 | Sprints 2–3 | To Do |
| [SNX-19](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-19) | Establish delivery gates and stabilize the frozen release | QA | P0 | Sprints 2–4 | To Do |

Reused planning story [SNX-15](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-15): **[DOCS] Plan and verify the Phase 1–2 delivery backlog**, P0, Sprint 2 preparation, no prerequisites, parent [SNX-19](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-19), Unassigned; moved to **In Review** after read-back verification. Team review/capacity confirmation remains its closure criterion.

The table below lists prerequisite completion, not a prohibition on starting against agreed mocks/contracts. All entries are **Unassigned**.

| Issue | Type | Title | Category | Priority | Target sprint | Due / decision | Dependencies | Status |
|---|---|---|---|---|---|---|---|---|
| [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) | Task | Resolve scope gaps and publish data/API contracts | DOCS | P0 | Sprint 2 | 2026-10-19 | — | To Do |
| [SNX-21](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-21) | Task | Spike: prove Gmail OAuth and synthetic mailbox ingestion | INTEGRATION | P0 | Sprint 2 | 2026-10-20 | — | To Do |
| [SNX-22](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-22) | Task | Spike: prove Facebook Page conversation access and review path | INTEGRATION | P0 | Sprint 2 | 2026-10-21 | — | To Do |
| [SNX-23](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-23) | Task | Spike: validate Viber bot access against the client's conversation workflow | INTEGRATION | P0 | Sprint 2 | 2026-10-21 | — | To Do |
| [SNX-24](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-24) | Task | Spike: select and evaluate structured LLM extraction | INTEGRATION | P0 | Sprint 2 | 2026-10-22 | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) | To Do |
| [SNX-25](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-25) | Task | Spike: validate AWS S3 access, hosting and alert delivery | DEVOPS | P0 | Sprint 2 | 2026-10-22 | — | To Do |
| [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26) | Task | Implement bronze schema, lead identity mapping and repeatable migrations | DATA | P0 | Sprint 2 | 2026-10-21 | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) | To Do |
| [SNX-27](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-27) | Story | Implement two-user login and protect application APIs | BACKEND | P0 | Sprint 2 | 2026-10-23 | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20), [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26) | To Do |
| [SNX-28](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-28) | Story | Import synthetic Facebook and Viber exports into bronze | INTEGRATION | P0 | Sprint 2 | 2026-10-23 | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20), [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26), [SNX-27](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-27) | To Do |
| [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29) | Task | Build dbt silver leads and interactions with baseline status parsing | DATA | P0 | Sprint 2 | 2026-10-26 | [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26) | To Do |
| [SNX-30](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-30) | Task | Expose authenticated lead, due-today and history queries | BACKEND | P0 | Sprint 2 | 2026-10-27 | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20), [SNX-27](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-27), [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29) | To Do |
| [SNX-31](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-31) | Story | Deliver the due-today dashboard and searchable lead history | FRONTEND | P0 | Sprint 2 | 2026-10-28 | [SNX-27](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-27), [SNX-30](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-30) | To Do |
| [SNX-32](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-32) | Task | Implement incremental Gmail ingestion with replay protection | INTEGRATION | P0 | Sprint 2 | 2026-10-27 | [SNX-21](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-21), [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26) | To Do |
| [SNX-33](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-33) | Task | Orchestrate Gmail and bronze-to-silver runs in Airflow | DATA | P0 | Sprint 2 | 2026-10-29 | [SNX-32](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-32), [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29) | To Do |
| [SNX-34](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-34) | Task | Add reproducible checks and a shared test deployment | DEVOPS | P0 | Sprint 2 | 2026-10-23 | [SNX-25](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-25) | To Do |
| [SNX-35](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-35) | Task | Verify the first complete Phase 1 workflow and Sprint 2 exit | QA | P0 | Sprint 2 | 2026-10-30 | [SNX-28](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-28), [SNX-31](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-31), [SNX-33](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-33), [SNX-34](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-34) | To Do |
| [SNX-36](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-36) | Task | Ingest synthetic Facebook Page conversations automatically | INTEGRATION | P1 | Sprint 3 | 2026-11-13 | [SNX-22](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-22), [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26) | To Do |
| [SNX-37](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-37) | Task | Ingest synthetic Viber bot messages through verified callbacks | INTEGRATION | P1 | Sprint 3 | 2026-11-13 | [SNX-23](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-23), [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26), [SNX-34](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-34) | To Do |
| [SNX-38](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-38) | Task | Integrate validated LLM enrichment into the silver pipeline | BACKEND | P1 | Sprint 3 | 2026-11-13 | [SNX-24](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-24), [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29) | To Do |
| [SNX-39](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-39) | Task | Archive raw conversations to private S3 with replay and reconciliation | DATA | P1 | Sprint 3 | 2026-11-12 | [SNX-25](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-25), [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26) | To Do |
| [SNX-40](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-40) | Task | Build gold conversion and response metrics with authenticated APIs | DATA | P1 | Sprint 3 | 2026-11-13 | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20), [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29), [SNX-30](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-30) | To Do |
| [SNX-41](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-41) | Story | Show conversion and response metrics in a minimal analytics view | FRONTEND | P1 | Sprint 3 | 2026-11-17 | [SNX-40](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-40), [SNX-27](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-27) | To Do |
| [SNX-42](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-42) | Task | Notify failed pipeline runs and surface last successful sync | BACKEND | P1 | Sprint 3 | 2026-11-16 | [SNX-25](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-25), [SNX-33](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-33), [SNX-31](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-31) | To Do |
| [SNX-43](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-43) | Task | Verify Phase 1–2 acceptance and freeze the November 20 candidate | QA | P0 | Sprint 3 | 2026-11-20 | [SNX-35](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-35), [SNX-36](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-36), [SNX-37](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-37), [SNX-38](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-38), [SNX-39](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-39), [SNX-41](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-41), [SNX-42](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-42) | To Do |
| [SNX-44](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-44) | Task | Run frozen-release regression and verify critical defect fixes | QA | P0 | Sprint 4 | 2026-12-02 | [SNX-43](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-43) | To Do |
| [SNX-45](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-45) | Subtask | Verify keyboard access, responsive tables and UI error recovery | QA | P1 | Sprint 4 | 2026-12-02 | [SNX-43](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-43) | To Do |
| [SNX-46](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-46) | Task | Verify access controls, recovery and performance of the frozen build | QA | P0 | Sprint 4 | 2026-12-03 | [SNX-43](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-43) | To Do |
| [SNX-47](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-47) | Task | Verify deployment and finalize the release runbook and demo | DOCS | P0 | Sprint 4 | 2026-12-04 | [SNX-44](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-44), [SNX-45](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-45), [SNX-46](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-46) | To Do |
| [SNX-48](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-48) | Story | Decision-gated: add manual clinic creation for outbound leads | FRONTEND | P2 | Future | — | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) | To Do |
| [SNX-49](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-49) | Story | Decision-gated: log calls and correct status or follow-up dates | BACKEND | P2 | Future | — | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) | To Do |
| [SNX-50](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-50) | Story | Decision-gated: persist dashboard table collapse preferences | FRONTEND | P3 | Future | — | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) | To Do |
| [SNX-51](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-51) | Story | Deferred: add the optional AWS cost reporting workflow | BACKEND | P3 | Future | — | — | To Do |
| [SNX-52](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-52) | Story | Deferred: send the optional daily follow-up digest | BACKEND | P3 | Future | — | — | To Do |

### Jira capability limitations

- Native sprint/board listing, creation and assignment are not exposed by the connected MCP tools, and no Sprint field appears in creation metadata or existing issue data. JQL found no SNX issue with a sprint association; empty sprint containers cannot be enumerated. Targets are preserved in **sprint-2 / sprint-3 / sprint-4 / sprint-future labels**, descriptions and native start/due dates. **These are not native sprint assignments.**
- Epic/Subtask creation metadata did not advertise priority (or Subtask dates), but issue edit supported them; all priorities and planned dates were set and verified natively.
- Spike and Bug types are not configured in the exposed SNX issue types. Research uses Task + `spike`; future observed defects should use Task + `bug` with reproduction/severity/expected/actual information unless Bug is enabled. No invented defect tickets were created.
- Existing `documentation` labels were preserved as a convention alongside primary `DOCS`. No component convention exists in the inspected backlog.
- Rovo general-content search returned access denied; Jira JQL/project/issue tools worked and were used for complete backlog inspection.
- Two link calls timed out. Each target issue was read before retry; the absent links were then created. Final verification found exactly the expected 55 distinct links.

## D. Critical path and parallel development

**Core slice:** [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) → [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26) → [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29) → [SNX-30](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-30) → [SNX-31](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-31) → [SNX-35](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-35). Auth [SNX-27](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-27) and imports [SNX-28](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-28) join this path. The live-email branch is [SNX-21](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-21) + schema → [SNX-32](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-32) → [SNX-33](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-33) → Phase 1 gate.

**Phase 2 integration gate:** Facebook [SNX-36](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-36), Viber [SNX-37](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-37), LLM [SNX-38](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-38), S3 [SNX-39](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-39), analytics [SNX-41](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-41) and alerts [SNX-42](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-42) converge at [SNX-43](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-43) on November 20. Their individual access gates do not block the dashboard, manual import or baseline silver work.

Parallel work is feasible as follows:

- Gmail, Facebook, Viber and cloud access research starts independently while contracts are settled.
- Once the first contract/fixtures are published, frontend/API consumers can develop against mocks; schema/dbt/auth/import implementation can overlap. Acceptance still requires the actual integrated components.
- Gmail does not wait for Facebook/Viber. S3 archival does not gate durable PostgreSQL ingestion. Invalid/unavailable LLM output leaves the baseline view usable.
- Gold models use contract-conformant silver fixtures and need not wait for live Facebook/Viber or LLM. Their final metrics still need genuine input coverage disclosed.
- Sprint 4 browser testing and security/recovery testing can run alongside regression. Final release documentation can be drafted earlier; completion waits for verified results.

Main bottlenecks are late contract decisions, incorrect identity/status-history design, test-account access, shared HTTPS hosting for callbacks and integration arriving after November 13–17. Publish incremental contracts rather than waiting for a perfect comprehensive design. If gold metrics cannot be supported by recorded history, report insufficient data rather than relabeling current-status counts as historical conversion.

## E. Risk register and contingency plan

The dates below are decision points, not promised approval dates. All external credentials are currently unavailable. Use team-controlled accounts and synthetic conversations for each access test. A fallback may keep the application demonstrable while leaving a required feature unfinished.

### Delivery and scope

**Team capacity — high uncertainty.** Two development sprints remain for work the proposal spread across two semesters. Available hours are unknown, so the full Phase 2 scope may not fit. [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) records capacity and scope by **October 19**; [SNX-35](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-35) reforecasts by **October 30**. Reserve time for integration and defects, defer optional work first, and seek an explicit scope exception if mandatory work still does not fit.

**Wireframe features without approved requirements — confirmed gap.** Manual clinic creation and call logging may be valuable for phone-based outreach, but the formal requirements do not define them. [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) records a decision by **October 19**. [SNX-48](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-48) and [SNX-49](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-49) remain unscheduled unless a requirement and capacity tradeoff are approved. Collapse controls and advanced filters stay deferred.

**Late integration — high schedule risk.** Features first connected near November 20 leave little time to find defects before Sprint 4. [SNX-35](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-35) checks the first complete workflow by **October 30**; missed Phase 2 targets are escalated on **November 13–17**; [SNX-43](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-43) decides release readiness on **November 20**. Start end-to-end checks by November 16 and keep a resettable synthetic demo. Report unfinished features as gaps rather than moving them into Sprint 4.

### External services

**Gmail — high access uncertainty.** Without working OAuth and mailbox access, the required automated Phase 1 source cannot run. [SNX-21](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-21) must read a real synthetic test thread and prove token refresh by **October 20**. [Google's Gmail scope guidance](https://developers.google.com/workspace/gmail/api/auth/scopes) identifies scopes that can require verification. Fixtures and manual imports let dashboard work continue if access fails, but **FR-01 remains unmet**. Client Workspace access is a separate check.

**Facebook Messenger — high access uncertainty.** A test Page may allow role-limited tests without the access needed for intended production conversations. [SNX-22](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-22) proves the API flow with a synthetic Page conversation and records its permission/review path by **October 21**; implementation evidence is due **November 13**. [Meta's Messenger Conversations reference](https://www.postman.com/meta/messenger-platform-api/folder/22794852-255610cd-47f5-4f4d-b3fa-71aec360be9a) describes Page permissions and advanced access. If access fails, keep export uploads; **FR-11 remains unmet**.

**Viber — high access and workflow uncertainty.** A personal account may not provide a bot, and bot callbacks may not cover the client's existing conversations. [SNX-23](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-23) must receive a real synthetic bot message and confirm conversation coverage by **October 21**; implementation evidence is due **November 13**. [Viber's API documentation](https://developers.viber.com/docs/api/rest-bot-api/) describes commercial bot creation, token authentication and certified HTTPS callbacks. If access or coverage fails, keep manual imports and flag **FR-12 as unmet**.

**LLM extraction — high access and quality uncertainty.** Provider access, cost or inaccurate output could delay FR-13 or give staff wrong follow-up dates. [SNX-24](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-24) evaluates schema-valid output on agreed synthetic examples by **October 22**; implementation evidence is due **November 13**. Validate results, keep unknown values explicit and retain baseline parsing if the model fails. Baseline parsing keeps the core usable but **does not complete FR-13**.

**AWS, hosting and alerts — high access uncertainty.** Missing accounts, budget or a notification route could block S3, failure alerts or the hosted demo. [SNX-25](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-25) tests each service separately by **October 22**. Keep raw messages in PostgreSQL and replay pending S3 archives after an outage; local Compose supports a demo. Actual S3 evidence is due **November 12** and alert delivery by **November 16**. Local substitutes do **not** complete FR-14 or FR-18.

### Data correctness

**Clinic identity and dbt rebuilds — medium to high technical risk.** Loose matching can merge two clinics or split one clinic's history; later manual corrections could vanish during a dbt rebuild. [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) defines identity and ownership rules by **October 19**. [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26) and [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29) test duplicate and ambiguous examples by **October 26**. Keep uncertain matches separate and store any staff corrections outside rebuilt dbt tables.

**Analytics definitions and missing history — high specification uncertainty.** Current status cannot prove that a lead passed through every funnel stage, and response time needs message direction and timestamps. [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20) agrees on formulas and required events by **October 19**; [SNX-40](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-40) checks hand-calculated examples by **November 13**. Show insufficient data where history is missing instead of inventing conversion or response-time values.

Each access spike must record the exact permissions, quotas, API versions and review steps for the chosen accounts. No external approval lead time is assumed.

## F. Scope protection

**Must Deliver:** FR-01–15 and FR-18, all NFRs, essential contracts/auth/data quality, live test-channel evidence, core workflow and stabilization. An API NO-GO does not demote a mandatory requirement to optional.

**Should Deliver, currently unscheduled:** manual clinic creation [SNX-48](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-48) and call logging/status/date corrections [SNX-49](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-49), only with an amended requirement and a credible capacity tradeoff. Their absence should be discussed as a product-utility limitation.

**Stretch / Deferred:** collapse persistence [SNX-50](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-50), finance/Cost Explorer [SNX-51](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-51) and daily digest [SNX-52](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-52). Advanced multi-condition filtering, expanded analytics and browser-triggered pipeline retry are not introduced as requirements. Do not spend contingency on them.

When constrained, first retain the baseline Gmail/manual-import workflow and drop optional/unapproved work. If external access prevents mandatory Phase 2, demonstrate the functioning core with transparent mocks/imports and secure an explicit scope exception. Such a result is a useful reduced-scope release, **not complete Phase 1–2 compliance**.

## G. Final delivery assessment

A stable core demonstration by November 20 is plausible if the October 19 contracts, October 20 Gmail access and October 30 Phase 1 gate pass. The plan deliberately brings a complete workflow forward and keeps Sprint 4 free of new feature development.

**A guaranteed full Phase 1–2 release is not supportable from the current evidence.** The repository is a scaffold, every external credential is unavailable, Viber may not match the original conversation workflow, and team availability is unmeasured. The complete target is conditional on early provider GO decisions and sufficient parallel capacity. If any must-deliver requirement misses the November 20 gate, report the requirement gap and seek a scope exception rather than relabeling mocks as completion or scheduling features during stabilization.

Test accounts are appropriate for development and academic demonstrations. Production use with SolTech's actual Workspace/Page/bot accounts, real data permissions and operational credentials requires separate evidence before claiming client readiness.

## Verification evidence

Independent Jira read-back checked all 38 planned issues: types, parent hierarchy, native priorities, unassigned assignees, category/priority/sprint labels, due/start dates and all seven required description sections. Both directions of all 55 Blocks links match the planned graph. The graph is acyclic and no prerequisite due date is later than its dependent. Native sprint association is explicitly unsupported and was not claimed.

[Machine-readable plan](jira_backlog_plan.json) includes exact ticket text and key mappings. The verification JSON is a local, ignored point-in-time snapshot; the durable check results are recorded above. Application tests were not run because no application code was changed.

## Requirement coverage

| Requirement | Deliverable | Jira coverage |
|---|---|---|
| FR-01 | Live test Gmail ingestion | [SNX-21](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-21), [SNX-32](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-32), [SNX-33](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-33) |
| FR-02 | Facebook/Viber manual export upload | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20), [SNX-28](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-28) |
| FR-03 | Immutable raw PostgreSQL messages | [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26), [SNX-28](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-28), [SNX-32](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-32) |
| FR-04 | dbt silver leads/interactions | [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29) |
| FR-05 | Airflow schedules/retries | [SNX-33](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-33) |
| FR-06 | FastAPI serving | [SNX-30](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-30) |
| FR-07 | Due-today lead view | [SNX-30](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-30), [SNX-31](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-31) |
| FR-08 | Complete lead history | [SNX-30](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-30), [SNX-31](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-31) |
| FR-09 | Status/next-action filters | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20), [SNX-30](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-30), [SNX-31](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-31) |
| FR-10 | Two-user authentication | [SNX-27](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-27) |
| FR-11 | Live test Facebook Page ingestion | [SNX-22](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-22), [SNX-36](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-36) |
| FR-12 | Live test Viber bot ingestion | [SNX-23](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-23), [SNX-37](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-37) |
| FR-13 | Real LLM extraction | [SNX-24](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-24), [SNX-38](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-38) |
| FR-14 | Actual private S3 retention | [SNX-25](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-25), [SNX-39](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-39) |
| FR-15 | dbt gold metrics and view | [SNX-40](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-40), [SNX-41](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-41) |
| FR-16 | Optional finance | [SNX-51](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-51) |
| FR-17 | Optional digest | [SNX-52](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-52) |
| FR-18 | Actual failure notifications | [SNX-25](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-25), [SNX-42](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-42) |
| NFR-01 | Identity consistency/deduplication | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20), [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26), [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29), [SNX-44](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-44) |
| NFR-02 | Retries/recovery | [SNX-33](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-33), [SNX-39](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-39), [SNX-42](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-42), [SNX-46](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-46) |
| NFR-03 | Authentication/privacy | [SNX-27](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-27), [SNX-25](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-25), [SNX-46](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-46) |
| NFR-04 | Immediate follow-up actionability | [SNX-31](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-31), [SNX-45](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-45) |
| NFR-05 | Searchable history | [SNX-30](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-30), [SNX-31](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-31), [SNX-45](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-45) |
| NFR-06 | Layered, maintainable pipeline | [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26), [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29), [SNX-40](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-40), [SNX-47](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-47) |
| NFR-07 | Independent source adapters | [SNX-20](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-20), [SNX-28](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-28), [SNX-32](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-32), [SNX-36](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-36), [SNX-37](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-37) |
| NFR-08 | Run monitoring/alerting | [SNX-33](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-33), [SNX-42](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-42), [SNX-46](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-46) |
| NFR-09 | Raw source/time lineage | [SNX-26](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-26), [SNX-29](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-29), [SNX-39](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-39), [SNX-40](https://jemarcobriz123-1788442076746.atlassian.net/browse/SNX-40) |
