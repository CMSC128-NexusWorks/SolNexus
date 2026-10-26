# Software Requirements List

## Unified Lead & Client Communication Intelligence Pipeline

Prepared for SolTech EMR | CMSC 128 / CMSC 129 (SWE 1 & SWE 2) | September 10, 2026

---

## 1. Functional Requirements

Requirements are grouped by delivery phase. Phase 1 is the minimum finished product for this semester; Phase 2 is pursued after Phase 1 is accepted, as capacity and external access allow. Existing requirement IDs remain stable, so later Phase 1 requirements use FR-19–FR-21. The expanded FR-21 delivery scope still needs a team capacity review.

### 1.1 Phase 1 — Foundational Pipeline and MVP Dashboard

| ID | Requirement |
|---|---|
| FR-01 | **Automated Email Ingestion** — The system shall automatically ingest lead-related email conversations from SolTech's Google Workspace account via the Gmail API. An initial message with no staff-confirmed clinic association shall remain unlinked and shall create or update an actionable inquiry with an explicitly unknown clinic name. |
| FR-02 | **Existing Lead Spreadsheet Import** — Authorized staff shall be able to upload SolTech's existing lead spreadsheet (the format represented by `leads-data/Leads Spreadsheet.xlsx`) to initialize clinic/lead records in SolNexus. Both “Ljs Calling Sheet” and “Jacks Calling Sheet” are equally authoritative migration inputs with separate adapters and staff review of conflicting values. LJ's column H contains notes and I contains the person Sir LJ spoke to; neither establishes a clinic name. After migration, staff shall manage and track leads in SolNexus rather than use the spreadsheet as an ongoing source of truth. The import shall validate rows and report rejected or review-needed rows. Re-uploading shall not create duplicate leads or overwrite SolNexus edits. Repeated or differently written clinic rows follow the SNX-20 staff-confirmed identity rule. Spreadsheet rows are lead data, not conversation messages; a blank facility in the workbook is rejected rather than converted into a first-contact inquiry. |
| FR-03 | **Raw Message Storage (Bronze Layer)** — The system shall store all ingested messages in their original, unmodified form in a PostgreSQL bronze layer, tagged with source channel and timestamp. |
| FR-04 | **Data Transformation (Silver Layer)** — The system shall transform bronze messages and durable operational lead data into normalized, structured "leads" and "interactions" tables using dbt models. The lead view shall include confirmed clinics and open unknown-name inquiries; dbt rebuilds shall preserve staff-entered operational values and unresolved message links. |
| FR-05 | **Pipeline Orchestration** — The system shall use Apache Airflow to schedule and orchestrate ingestion and transformation runs, including automatic retries on failure. |
| FR-06 | **Backend API** — The system shall expose authenticated leads, inquiries and interactions reads, plus version-checked operational row updates and staff-confirmed clinic-name transitions, through a FastAPI REST backend consumed by the web dashboard. |
| FR-07 | **"Leads to Follow Up Today" View** — The dashboard shall display a prioritized list of leads whose next-action/follow-up date is due, showing the confirmed clinic name or an explicit **Clinic name unknown** label, contact person, contact number, and current topic/status. Unknown-name inquiries without a date shall appear in a visible **Needs clinic name** action group on initial load. |
| FR-08 | **"All Leads" / Complete Lead History View** — The dashboard shall display confirmed clinics and open inquiries with their available interaction history, clinic name or explicit unknown state, contact person, contact number, engagement topic, current status, follow-up date, and prior linked interactions. Unlinked messages shall remain in staff review rather than be shown as another clinic's history. |
| FR-09 | **Status Filtering** — The system shall allow users to filter the lead list by current status or required next action (e.g., proposal sent, awaiting demo, follow-up needed). |
| FR-10 | **User Authentication** — The system shall require login authentication and shall support the two designated SolTech team members who manage lead tracking. Dashboard reads, row edits, imports, exports and identity confirmations shall require authorized staff access. |
| FR-19 | **Lead Spreadsheet Download** — Authorized staff shall be able to download a current lead snapshot using documented columns corresponding to the existing lead sheet where applicable. The export shall reflect edited operational values for imported and manually created clinics and open inquiries. An inquiry's clinic name shall be blank with an explicit `clinic_name_state=unknown`; the export shall not represent conversation history as spreadsheet rows or include raw messages. |
| FR-20 | **Manual Clinic Creation** — Authorized staff shall be able to create a named clinic lead before any digital conversation arrives, as shown in wireframe 06. The form shall capture clinic name and allow contact person, contact number, email address, status, next-action date, and how the clinic was found. The clinic shall appear in the dashboard and survive pipeline rebuilds; later channel interactions shall attach only under the staff-confirmed source-identity rule. |
| FR-21 | **Editable Dashboard Rows and Clinic-Name Confirmation** — Authorized staff shall be able to edit operational row values in the Due today, Needs clinic name and All leads dashboard views with spreadsheet-like controls, save/cancel, field validation, an audit trail, and stale-edit protection. Editable values include contact details, status, next-action date, notes, person spoken to and confirmed clinic fields; derived message fields remain read-only. A first-contact inquiry shall show **Clinic name unknown** and an **Email to ask** action. Staff may confirm its clinic name only after reviewing SolTech's question and the lead's reply, then explicitly associate the source identity with a clinic. The initial lead message shall not populate the confirmed clinic name. Edits and confirmations shall persist through pipeline rebuilds. Call logging, snooze and table-collapse preferences are separate decisions. |

### 1.2 Phase 2 — Multi-Source Automation, Intelligence & Analytics

Phase 2 implementation starts only after Phase 1 acceptance. Provider access work and connector delivery are not Phase 1 acceptance dependencies.

| ID | Requirement |
|---|---|
| FR-11 | **Automated Facebook Messenger Ingestion** — After a Phase 2 access and review-path decision, the system shall automatically ingest accessible Facebook Page conversations through the Facebook Graph API into the shared pipeline. A first-contact message with no confirmed clinic mapping shall remain unlinked and produce an explicitly unknown-name inquiry. Phase 2 acceptance requires a real API test with synthetic conversations; a mock alone does not satisfy this requirement. |
| FR-12 | **Automated Viber Ingestion** — Subject to an evidenced access and conversation-coverage decision, the system shall automatically ingest supported Viber bot conversations through the Viber Bot/REST API. The Phase 1 lead spreadsheet does not satisfy this conversation-ingestion requirement. |
| FR-13 | Use an LLM to read each conversation and convert what the client said into structured fields that the rest of our data pipeline can use. |
| FR-14 | **Data Lake Storage** — The system shall extend raw conversation storage to Amazon S3 as the bronze/raw layer for scalable retention of unstructured source data. |
| FR-15 | **Conversion & Performance Analytics (Gold Layer)** — The system shall generate dbt-modeled analytics tables reporting the lead conversion funnel (contacted → proposal sent → demo → closed) and response-time metrics. |
| FR-16 | **Financial Tracking Module (Stretch Goal)** — The system may ingest AWS Cost Explorer billing data, and optionally manual expense entries, into a lightweight reporting view. This is a lower-priority, stretch-goal requirement per the client's stated priorities. |
| FR-17 | **Daily Digest Notification (Stretch Goal)** — The system may send a daily email digest summarizing that day's required follow-ups. |
| FR-18 | **Pipeline Failure Alerting** — The system shall alert the team when a scheduled Airflow DAG run fails. The system shall notify the team if a scheduled data process fails to complete successfully. |

## 2. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | **Data Consistency & Deduplication** — The pipeline shall standardize and de-duplicate lead information gathered from different channels into a single, consistent lead record, avoiding fragmentation of a lead's history across sources. |
| NFR-02 | **Pipeline Reliability** — Scheduled ingestion and transformation jobs shall support automatic retries on failure (Phase 1) and shall notify the team of failed runs (Phase 2), reducing silent data loss. |
| NFR-03 | **Access Control & Privacy** — The dashboard and underlying lead/client data shall be accessible only to authenticated, authorized SolTech users, given that the data relates to clinic clients of a healthcare technology company. |
| NFR-04 | **Usability — Immediate Actionability** — Upon login, a user shall be able to identify, without additional navigation or filtering, which clinics require contact that day, directly replacing the manual spreadsheet lookup process. |
| NFR-05 | **Searchability** — Users shall be able to locate a specific lead's history and status without manually scanning a spreadsheet, via the "All Leads" filterable view. |
| NFR-06 | **Maintainability** — The pipeline shall follow a layered (bronze/silver/gold) data architecture with modular dbt transformation models, so that individual layers and models can be modified or extended independently. |
| NFR-07 | **Scalability of Data Source Integration** — The architecture shall accommodate additional communication channels and increasing data volume, beginning with automated Gmail in Phase 1 and adding Facebook and Viber automation in Phase 2 without redesigning the core data model. |
| NFR-08 | **Observability** — The orchestration layer shall provide basic monitoring of pipeline runs in Phase 1, extended to alerting on failures in Phase 2, so pipeline health is visible to the team. |
| NFR-09 | **Data Traceability** — Every ingested record shall retain its originating source channel and timestamp through the bronze layer, so that any lead or interaction can be traced back to its origin. |

## 3. Requirements Summary

| Category | Count |
|---|---|
| Functional Requirements — Phase 1 | 13 (FR-01 – FR-10, FR-19 – FR-21) |
| Functional Requirements — Phase 2 | 8 (FR-11 – FR-18; FR-16 and FR-17 are stretch goals) |
| **Total Functional Requirements** | **21** |
| **Total Non-Functional Requirements** | **9** |
| **Overall Total** | **30** |
