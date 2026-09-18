# SolNexus

SolNexus is a unified lead and client communication pipeline for SolTech EMR. It brings lead conversations from email, Facebook Messenger, and Viber into one searchable system, helping the team track follow-ups and client history without relying on a manually maintained spreadsheet.

## Project Goals

- Centralize lead and interaction data from multiple communication channels.
- Show which leads need follow-up today.
- Provide a searchable history of all leads and conversations.
- Automate ingestion, transformation, and pipeline monitoring.
- Support future analytics and AI-assisted lead classification.

## Planned Phases

### Phase 1: MVP

- Gmail API ingestion, with manual imports for Facebook and Viber exports.
- PostgreSQL bronze storage and dbt silver models for leads and interactions.
- Airflow orchestration with retries.
- FastAPI backend and React dashboard.
- Authentication for SolTech staff.

### Phase 2: Expansion

- Automated Facebook Messenger and Viber integrations.
- LLM-based extraction of lead status, next actions, and urgency.
- Amazon S3 raw data lake and dbt gold analytics models.
- Conversion funnel and response-time reporting.
- Pipeline failure alerts and optional finance tracking and daily digest features.

## Architecture

The system follows a bronze/silver/gold data architecture:

```mermaid
flowchart LR
    subgraph EXTRACT["Extraction"]
        E1["Gmail API"]
        E2["Facebook Graph API"]
        E3["Viber Bot/REST API"]
        E4["AWS Cost Explorer API\n(stretch)"]
    end

    subgraph ORCH["Orchestration (Airflow)"]
        DAG1["ingest_* DAGs\n(per source, scheduled)"]
        DAG2["extract_and_classify DAG"]
        DAG3["transform_silver_to_gold DAG"]
        ALERT["on_failure_callback\n→ team notification"]
    end

    subgraph BRONZE_L["Bronze / Raw Layer"]
        S3["Amazon S3\n(raw conversation objects)"]
        RAWPG["PostgreSQL\nraw_messages"]
    end

    subgraph LLM_L["Intelligence Layer"]
        LLM["LLM Extraction & Classification\n(status, next action, urgency)"]
    end

    subgraph SILVER_L["Silver Layer (dbt)"]
        LEADS["leads"]
        INTER["interactions"]
    end

    subgraph GOLD_L["Gold Layer (dbt)"]
        FUNNEL["conversion_funnel\n(contacted → proposal →\ndemo → closed)"]
        RESPTIME["response_time_metrics"]
    end

    subgraph FIN_L["Finance (stretch)"]
        FINVIEW["billing_summary"]
    end

    E1 --> DAG1
    E2 --> DAG1
    E3 --> DAG1
    E4 --> DAG1
    DAG1 --> S3
    DAG1 --> RAWPG
    DAG1 -- "failure" --> ALERT

    S3 --> DAG2
    RAWPG --> DAG2
    DAG2 --> LLM
    LLM --> LEADS
    LLM --> INTER

    LEADS --> DAG3
    INTER --> DAG3
    DAG3 --> FUNNEL
    DAG3 --> RESPTIME
    DAG3 -- "failure" --> ALERT

    E4 --> FINVIEW
```

The dashboard provides two core views: **Leads to Follow Up Today** and **All Leads**.

## Technology Stack

- **Backend:** FastAPI and Python
- **Frontend:** React
- **Data:** PostgreSQL, dbt, and Amazon S3 (Phase 2)
- **Pipeline:** Apache Airflow
- **Integrations:** Gmail API, Facebook Graph API, Viber API, and AWS Cost Explorer

## Documentation

- [Project Proposal](docs/project_proposal.md)
- [Software Requirements](docs/software_requirements.md)
- [System Architecture](docs/architecture.md)
