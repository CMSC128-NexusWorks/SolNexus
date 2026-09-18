# PROJECT PROPOSAL

## Unified Lead & Client Communication Intelligence Pipeline

**A Data Engineering Solution for SolTech EMR**

- **Prepared for:** SolTech EMR
- **Course:** CMSC 128 / CMSC 129 (SWE 1 & SWE 2)
- **Team Members:**  Briz, Borbolla, Caballero, Salomeo, Guevara


---

## 1. Executive Summary

SolTech EMR is a healthcare technology startup that manages sales outreach to clinics through multiple, disconnected communication channels — Facebook Messenger, Viber, and email — with lead information recorded manually in a spreadsheet by two team members. As the company grows, this manual process has become error-prone and difficult to search, and the founder has identified client/lead tracking as the single most valuable problem to solve, ahead of secondary concerns such as financial tracking.

This proposal outlines a two-semester Data Engineering project that will design and build a Unified Lead & Client Communication Intelligence Pipeline: an automated system that ingests conversation data from SolTech's communication channels, transforms it into a clean and structured data model, and surfaces it through a purpose-built web dashboard. The dashboard directly implements the two-table view requested by the client — a "Leads to Follow Up Today" view and a "Complete Lead History" view — backed by a governed data pipeline rather than manual data entry.

In Semester 1 (SWE 1), the team will deliver a working end-to-end prototype: ingestion from email, an orchestrated pipeline built with Apache Airflow, transformation modeling with dbt, a normalized PostgreSQL data warehouse, and a functioning two-table web dashboard. In Semester 2 (SWE 2), the system will be extended with additional source integrations (Facebook Messenger and Viber), an AI/LLM-based extraction and classification layer, a lightweight financial tracking module, and analytics on lead conversion performance.

## 2. Client Background

SolTech EMR is a startup building an Electronic Medical Records (EMR) product for healthcare clinics in the Philippines. The company is led by a small founding team who personally handle outbound sales and client relationship management by contacting clinics directly through Facebook, Viber, and email. As a young company, SolTech does not yet have clean, structured data pipelines of the kind found in more established businesses (e.g., inventory or sales systems), which makes this an appropriate and realistic setting for a foundational Data Engineering project.

## 3. Problem Statement

Based on the client interview, SolTech's core operational pain point is the lack of a centralized system for tracking sales leads and client conversations. Conversations relevant to a single lead may occur across three separate, unconnected channels, and the only record of a lead's status is a manually updated spreadsheet maintained by two people. This creates several concrete problems:

- **No single source of truth:** a lead's history is fragmented across Facebook, Viber, email, and a spreadsheet.
- **Manual, error-prone updates:** status changes (e.g., "proposal sent," "awaiting demo," "call back in one week") are entered by hand and can be missed or forgotten.
- **No prioritization view:** there is no clear, immediate list of which clinics need to be contacted today.
- **Difficult search and recall:** with a large volume of clinic names and conversation history, it is hard to locate a specific lead's context quickly.
- **No visibility into pipeline performance:** there is no way to filter or report on leads by stage (e.g., all leads awaiting a demo).

A secondary, lower-priority problem raised by the client is the informal tracking of business expenses (e.g., AWS costs, salaries, ad hoc payments), which the client explicitly considers less urgent than lead tracking and is treated as a stretch goal in this proposal.

## 4. Project Objectives

The project aims to:

- Design and implement a data pipeline that ingests unstructured and semi-structured conversation data from multiple communication channels into a single, structured data store.
- Apply data engineering best practices — orchestration, modular transformation, and data modeling — using Apache Airflow and dbt.
- Build a web application that gives SolTech's team a real-time, prioritized view of leads requiring follow-up, and a complete, searchable history of all leads.
- Progressively increase the automation and intelligence of the pipeline across two semesters, moving from manual/semi-automated ingestion toward fully automated, AI-assisted lead extraction and classification.
- Deliver a system that provides immediate, measurable operational value to SolTech at the end of each semester.

## 5. Scope of Work

### 5.1 Semester 1 (SWE 1) — Foundational Pipeline and MVP Dashboard

The goal of Semester 1 is a working, demonstrable prototype that automates ingestion from at least one live communication channel, establishes the full orchestration and transformation stack, and delivers the two-table dashboard the client described in the interview.

**Planned deliverables:**

- Automated email ingestion via the Gmail API (SolTech uses Google Workspace), plus a manual/CSV import screen for Viber and Facebook conversation exports, to be used while API access for those channels is confirmed.
- A raw ("bronze") data layer in PostgreSQL that stores ingested messages in their original form, tagged by source and timestamp.
- Apache Airflow DAGs to orchestrate scheduled ingestion and transformation runs, including retries and basic monitoring.
- dbt models to transform bronze data into a clean, structured ("silver") layer: normalized lead and interaction tables.
- A FastAPI backend exposing REST endpoints for leads and interactions.
- A React web dashboard implementing the two views requested by the client:
  - **"Leads to Follow Up Today"** — clinics requiring action, with contact name, number, and current topic/status.
  - **"All Leads"** — the complete lead history with filtering by status (e.g., proposal sent, awaiting demo, follow-up needed).
- Basic authentication for the two SolTech team members who track leads.

By the end of Semester 1, SolTech will have a working system where email-based lead activity is automatically captured and reflected in the dashboard, replacing part of the manual spreadsheet workflow.

### 5.2 Semester 2 (SWE 2) — Full Automation, Intelligence, and Analytics

Semester 2 extends the Semester 1 foundation into a fully automated, multi-source pipeline with an added intelligence layer, closing the gaps intentionally deferred in Semester 1.

**Planned deliverables:**

- Automated ingestion from Facebook Messenger (Graph API) and Viber (Bot/REST API), removing the need for manual import.
- An LLM-based extraction and classification layer that reads unstructured message text and automatically determines lead status, next action, and urgency/sentiment — reducing manual encoding effort.
- Expansion of the bronze layer into a proper data lake (e.g., Amazon S3) for raw conversation storage prior to transformation.
- Additional dbt models forming a "gold" analytics layer: lead conversion funnel (contacted → proposal sent → demo → closed) and response-time metrics.
- A lightweight financial tracking module ingesting AWS Cost Explorer data (and optionally manual expense entries) into a simple reporting view (stretch goal, per client's stated priority).
- Optional daily digest notification (email) summarizing that day's required follow-ups.
- Performance, reliability, and monitoring improvements to the Airflow pipeline (alerting on failed DAG runs).

## 6. System Architecture

The system follows a layered data engineering architecture, moving data from raw, unstructured sources through progressively cleaner and more analysis-ready layers, and finally into an application layer that the client interacts with directly.

**Architecture overview:**

- **Source Systems:** Gmail (Google Workspace), Facebook Messenger, Viber, AWS Cost Explorer.
- **Ingestion Layer:** Python extraction scripts and API connectors, scheduled and orchestrated by Apache Airflow.
- **Storage — Bronze Layer:** raw, source-tagged messages stored in PostgreSQL (Semester 1) and Amazon S3 (Semester 2).
- **Transformation — Silver Layer:** dbt models that clean, deduplicate, and structure raw data into normalized lead and interaction tables.
- **Transformation — Gold Layer (Semester 2):** aggregated analytics tables for conversion funnel and performance metrics.
- **Serving Layer:** FastAPI REST backend exposing structured data to the frontend.
- **Application Layer:** React web dashboard (two-table lead view, filters, and Semester 2 analytics views).

This bronze/silver/gold structure is a widely used data engineering pattern (the medallion architecture) and allows the team to demonstrate a clear, industry-recognizable data pipeline design.

## 7. Technology Stack

| Layer | Semester 1 | Semester 2 (Extension) |
|---|---|---|
| Ingestion | Gmail API; manual/CSV import for Viber & Facebook | Facebook Graph API; Viber REST/Bot API; AWS Cost Explorer API |
| Orchestration | Apache Airflow | Apache Airflow (added monitoring & alerting) |
| Transformation | dbt (bronze → silver models) | dbt (added gold/analytics models) |
| Storage | PostgreSQL | PostgreSQL + Amazon S3 (raw data lake) |
| Intelligence Layer | Rule-based status parsing (baseline) | LLM-based extraction & classification |
| Backend API | FastAPI (Python) | FastAPI (Python) |
| Frontend | React | React (added analytics views) |
| Authentication | Basic login for 2 users | Basic login for 2 users |
| Deployment | AWS (EC2/RDS) or equivalent | AWS (EC2/RDS/ECS) or equivalent |

## 8. Data Sources & Integration Plan

| Source | Data Type | Access Method | Semester |
|---|---|---|---|
| Email (Gmail / Google Workspace) | Semi-structured text (threads, timestamps, sender) | Gmail API (OAuth) | 1 |
| Facebook Messenger (Page) | Unstructured chat text | Manual export (Sem 1) → Graph API (Sem 2) | 1 → 2 |
| Viber | Unstructured chat text | Manual export (Sem 1) → Bot/REST API (Sem 2) | 1 → 2 |
| AWS Billing | Structured cost data (CSV / API) | Cost Explorer API / CSV export | 2 (stretch) |

## 9. Data Model & Dashboard Design

The core data model is designed directly around the two-table view the client requested during the interview. At the silver layer, two primary entities are modeled:

- **leads** — one row per clinic/lead, containing: clinic name, primary contact person, contact number, current status (e.g., contacted, proposal sent, awaiting demo, closed), next action date, and source(s) of origin.
- **interactions** — one row per logged conversation event, containing: lead reference, channel (email/Viber/Facebook), message excerpt/topic, timestamp, and the team member involved.

These map directly onto the two dashboard views defined by the client:

- **"Leads to Follow Up Today"** — a filtered view of the leads table where `next_action_date` is due, sorted by priority.
- **"All Leads"** — the complete leads table with filtering by status, allowing the team to, for example, instantly see all leads that are "awaiting demo."

## 10. Project Timeline & Milestones (Not yet final)

### Semester 1 (SWE 1)

| Phase | Weeks | Key Milestones |
|---|---|---|
| Requirements & Design | 1–3 | Finalize data model, architecture diagram, Airflow/dbt project setup |
| Ingestion & Storage | 4–6 | Gmail API integration; bronze layer in PostgreSQL; manual import tool |
| Transformation | 7–9 | dbt silver models for leads and interactions; Airflow DAGs scheduled |
| Application Layer | 10–12 | FastAPI backend; React dashboard (two-table view); authentication |
| Testing & Demo | 13–14 | End-to-end testing; client walkthrough; MVP demo |

### Semester 2 (SWE 2)

| Phase | Weeks | Key Milestones |
|---|---|---|
| API Integrations | 1–4 | Facebook Graph API and Viber API automated ingestion |
| Intelligence Layer | 5–7 | LLM-based extraction & classification pipeline |
| Data Lake & Analytics | 8–10 | S3 raw storage; dbt gold models; conversion funnel analytics |
| Finance Module (stretch) | 11–12 | AWS cost ingestion and reporting view |
| Hardening & Final Demo | 13–14 | Monitoring/alerting, QA, client walkthrough, final demo |

## 11. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Facebook/Viber API access not granted in time | Delays automated multi-channel ingestion | Use manual/CSV import in Sem 1; pursue API access in parallel for Sem 2 |
| Unstructured chat text is noisy/inconsistent | Reduces accuracy of automated status extraction | Start with rule-based parsing in Sem 1; introduce LLM extraction with validation in Sem 2 |
| Limited team familiarity with dbt | Slower initial development pace | Team has prior Airflow experience and will onboard dbt early in Sem 1 with a small pilot model |
| Client's low prioritization of finance tracking | Feature may be deprioritized | Scoped explicitly as a Semester 2 stretch goal, not a core deliverable |

## 12. Expected Outcomes & Success Metrics

- A live dashboard replacing the manual spreadsheet for day-to-day lead follow-up by end of Semester 1.
- At least one communication channel (email) fully automated end-to-end by end of Semester 1.
- All three communication channels (email, Facebook, Viber) automated by end of Semester 2.
- Reduced manual data entry effort for the SolTech team, measured qualitatively through client feedback.
- A documented, orchestrated (Airflow + dbt) pipeline suitable for demonstration in academic and professional portfolios.

