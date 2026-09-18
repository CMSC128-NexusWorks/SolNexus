# Software Requirements List

## Unified Lead & Client Communication Intelligence Pipeline

Prepared for SolTech EMR | CMSC 128 / CMSC 129 (SWE 1 & SWE 2) | September 10, 2026

---

## 1. Functional Requirements

Requirements are grouped by delivery phase, consistent with the two-semester scope defined in the project proposal.

### 1.1 Phase 1 — Foundational Pipeline and MVP Dashboard

| ID | Requirement |
|---|---|
| FR-01 | **Automated Email Ingestion** — The system shall automatically ingest lead-related email conversations from SolTech's Google Workspace account via the Gmail API. |
| FR-02 | SolTech staff should be able to manually upload exported Viber/Facebook conversations into the system, instead of the system automatically connecting to those platforms. |
| FR-03 | **Raw Message Storage (Bronze Layer)** — The system shall store all ingested messages in their original, unmodified form in a PostgreSQL bronze layer, tagged with source channel and timestamp. |
| FR-04 | **Data Transformation (Silver Layer)** — The system shall transform bronze-layer data into normalized, structured "leads" and "interactions" tables using dbt models. |
| FR-05 | **Pipeline Orchestration** — The system shall use Apache Airflow to schedule and orchestrate ingestion and transformation runs, including automatic retries on failure. |
| FR-06 | **Backend API** — The system shall expose leads and interactions data through a FastAPI REST backend consumed by the web dashboard. |
| FR-07 | **"Leads to Follow Up Today" View** — The dashboard shall display a prioritized list of leads whose next-action/follow-up date is due, showing clinic name, contact person, contact number, and current topic/status. |
| FR-08 | **"All Leads" / Complete Lead History View** — The dashboard shall display the complete list of leads and their interaction history, including clinic name, contact person, contact number, engagement topic, current status, follow-up date, and prior interactions. |
| FR-09 | **Status Filtering** — The system shall allow users to filter the lead list by current status or required next action (e.g., proposal sent, awaiting demo, follow-up needed). |
| FR-10 | **User Authentication** — The system shall require login authentication and shall support the two designated SolTech team members who manage lead tracking. |

### 1.2 Phase 2 — Multi-Source Automation, Intelligence & Analytics

| ID | Requirement |
|---|---|
| FR-11 | **Automated Facebook Messenger Ingestion** — The system shall automatically ingest Facebook Messenger conversations via the Facebook Graph API, replacing the manual import process. |
| FR-12 | **Automated Viber Ingestion** — The system shall automatically ingest Viber conversations via the Viber Bot/REST API, replacing the manual import process. |
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
| NFR-07 | **Scalability of Data Source Integration** — The architecture shall be designed to accommodate additional communication channels and increasing data volume (e.g., extending from one automated source in Semester 1 to three in Semester 2) without a redesign of the core data model. |
| NFR-08 | **Observability** — The orchestration layer shall provide basic monitoring of pipeline runs in Phase 1, extended to alerting on failures in Phase 2, so pipeline health is visible to the team. |
| NFR-09 | **Data Traceability** — Every ingested record shall retain its originating source channel and timestamp through the bronze layer, so that any lead or interaction can be traced back to its origin. |

## 3. Requirements Summary

| Category | Count |
|---|---|
| Functional Requirements — Phase 1 | 10 (FR-01 – FR-10) |
| Functional Requirements — Phase 2 | 8 (FR-11 – FR-18) |
| **Total Functional Requirements** | **18** |
| **Total Non-Functional Requirements** | **9** |
| **Overall Total** | **27** |