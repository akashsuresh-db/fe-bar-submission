# Finance Operations Control Tower — Technical Overview

## Purpose and scope

This demo implements an end-to-end **Finance Operations “control tower”** on Databricks, spanning the three core finance workflows:

- **Procure-to-Pay (P2P / Accounts Payable)**
- **Order-to-Cash (O2C / Accounts Receivable)**
- **Record-to-Report (R2R / General Ledger & close)**

It showcases how Databricks can unify finance data into a governed lakehouse, operationalize it in a real-time application, and enable conversational analytics and automation using built-in AI capabilities and Databricks-native services.

This document is grounded in the repo contents provided. Where the repo explicitly states something is *not used* (e.g., Vector Search), that is called out.

---

## Key Databricks products used

### Lakehouse & governance
- **Delta Lake**: Storage format for Bronze/Silver/Gold tables.
- **Unity Catalog**: Central governance for tables and (optionally) files/volumes; enables permissions, auditability, and lineage.

### Data engineering
- **Lakeflow Declarative Pipelines (Delta Live Tables / DLT)**:
  - Implements **Bronze → Silver** transformations.
  - Uses **data quality expectations** and a quarantine pattern for invalid records.
  - Runs **serverless** with **Photon** enabled (per pipeline configuration).

### SQL & analytics
- **Databricks SQL Warehouse**:
  - Used by the application backend via the Databricks SQL connector.
  - Also used by Genie (space configuration requires a warehouse).

### AI & conversational experiences
- **Databricks AI Functions**:
  - Uses built-in SQL functions for document parsing and extraction (e.g., `ai_parse_document`, `ai_extract`) in the invoice AI processing step.
- **Databricks Model Serving / Serving Endpoints**:
  - Used for LLM-backed summarization and for the multi-agent supervisor integration (invoked via the serving endpoints REST API).
- **Databricks Genie**:
  - Provides natural-language analytics over curated Gold tables.
  - Genie spaces are created/configured via notebooks and/or UI; not deployable via Asset Bundles in this repo.

### Applications & operational state
- **Databricks Apps**:
  - Hosts a **React frontend** + **FastAPI backend** as a single app.
  - Uses **Server-Sent Events (SSE)** for real-time streaming UI updates.
- **Lakebase (managed Postgres)**:
  - Stores operational state: approvals, call logs, chat history/session memory.
  - The app supports an **in-memory fallback** if Lakebase is not configured.

### Automation & alerting
- **Databricks SQL Alerts (Alerts V2)**:
  - The app can “escalate” AP exceptions by creating/updating a SQL Alert and unpausing it to trigger email notifications.

### Deployment & repeatability
- **Databricks Asset Bundles (DAB)**:
  - Deploys the DLT pipeline, setup/teardown jobs, and the Databricks App.
  - Some components are explicitly **manual** (Genie space, multi-agent supervisor endpoint, Lakebase instance).

---

## High-level architecture

```text
                    ┌──────────────────────────────────────────────┐
                    │                Data Sources                  │
                    │  Synthetic ERP-like data + invoice documents │
                    └───────────────────────────┬──────────────────┘
                                                │
                                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Lakeflow Declarative Pipelines (DLT)                                         │
│  - Bronze: raw ingestion                                                     │
│  - Silver: cleansing/enrichment + DQ expectations + quarantine               │
└───────────────────────────┬──────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Gold layer (Delta tables)                                                    │
│  - P2P facts/dims (invoices, payments, vendors)                              │
│  - O2C facts/dims (collections, sales, customers)                            │
│  - R2R facts (GL, trial balance, reconciliation views)                       │
└───────────────┬───────────────────────────────┬──────────────────────────────┘
                │                               │
                ▼                               ▼
┌──────────────────────────────┐     ┌─────────────────────────────────────────┐
│ Databricks Genie              │     │ Databricks App (React + FastAPI)        │
│ - NL analytics over Gold      │     │ - KPI APIs via SQL Warehouse            │
│ - Curated questions/instr.    │     │ - SSE streams for AP/AR/GL operations   │
└───────────────┬──────────────┘     │ - Approvals/call logs/chat history       │
                │                    │   persisted to Lakebase                  │
                │                    └───────────────────┬─────────────────────┘
                │                                        │
                ▼                                        ▼
     ┌───────────────────────────┐          ┌───────────────────────────────┐
     │ Multi-agent supervisor     │          │ Lakebase (managed Postgres)   │
     │ (served via endpoint)      │          │ - approvals                    │
     │ - routes questions to tools│          │ - call logs                    │
     │ - returns formatted answer │          │ - chat session memory          │
     └───────────────────────────┘          └───────────────────────────────┘
```

---

## Data model and medallion flow (Bronze / Silver / Gold)

### Bronze (raw ingestion)
Bronze tables represent raw ERP-like extracts and raw invoice documents. In this demo, the raw data is generated by a setup notebook/job (synthetic dataset) and then processed by DLT.

Typical Bronze entities include:
- Vendor/customer masters
- Purchase orders, goods receipts, invoices, payments
- Sales orders, AR invoices, AR payments
- Chart of accounts, journal entries, cost centers
- Raw invoice documents (text/PDF-like content)

**Databricks products involved**
- Delta Lake tables governed by Unity Catalog
- DLT pipeline for ingestion into Bronze

### Silver (cleansed, validated, enriched)
Silver tables apply:
- Standardization and deduplication
- Business-rule validation via **DLT expectations**
- Quarantine patterns for invalid records (e.g., invoice exceptions, unbalanced journal entries)
- Enrichment such as match status and extracted invoice fields

Key Silver concepts implemented in the repo:
- **3-way matching** signals for P2P invoices (PO ↔ invoice ↔ receipt)
- **Invoice extraction outputs** (structured fields extracted from documents)
- **Exception/quarantine tables** used downstream by the app and alerting

**Databricks products involved**
- Lakeflow Declarative Pipelines (DLT) with expectations
- Delta Lake + Unity Catalog governance

### Gold (business-ready facts/dimensions)
Gold tables are curated for:
- KPI computation (touchless rate, aging, DSO, trial balance status)
- Operational dashboards (AP/AR/GL tabs)
- Conversational analytics (Genie)

Gold includes:
- P2P: vendor dimension, invoice fact, payment fact
- O2C: customer dimension, sales fact, collections fact
- R2R: GL fact, trial balance fact
- Reconciliation view(s) used to prove sub-ledger ↔ GL tie-out

**Databricks products involved**
- Spark SQL transformations (implemented as notebooks/jobs in this repo)
- Databricks SQL Warehouse for serving queries to the app and Genie

---

## Application layer (Databricks Apps)

### What the app provides
A single web application with three operational workbenches:
- **AP Operations**: invoice queue, exceptions, “verify before approve”, approvals, escalation
- **AR Operations**: collections queue, call logging outcomes (PTP/dispute/voicemail/escalate)
- **GL Operations**: journal entry validation stream, trial balance view, close checklist signals

### Backend (FastAPI)
The backend:
- Queries Gold/Silver tables through the **Databricks SQL connector** (SQL Warehouse).
- Streams operational events to the UI via **SSE endpoints**:
  - One stream per domain (AP/AR/GL).
- Integrates with:
  - **Lakebase** for operational writes (approvals, call logs, chat history).
  - **SQL Alerts V2** for escalation emails.
  - **Model Serving endpoints** for LLM summarization and multi-agent chat routing.

### Frontend (React)
The frontend:
- Renders KPI cards and operational queues.
- Uses **EventSource** to consume SSE streams.
- Includes an AI chat panel that streams responses from the backend (which itself streams chunks).

**Note on SSE reliability**
The repo includes explicit debugging guidance and UI improvements to surface SSE connection errors (rather than failing silently). This is important in real deployments where proxies/auth can affect EventSource behavior.

---

## AI capabilities in this demo

### 1) Invoice AI processing (structured extraction)
The repo includes a notebook-driven step that uses Databricks AI Functions to:
- Parse invoice documents into text/structure
- Extract key fields (invoice number, vendor, totals, tax IDs, PO reference, etc.)
- Persist extracted fields into Silver for downstream reconciliation and UI display

**Databricks products involved**
- Databricks AI Functions (`ai_parse_document`, `ai_extract`)
- Delta Lake tables (Silver extraction outputs)

### 2) “Verify before approve” credibility checks
The app exposes an API that performs a multi-source credibility check for a given invoice by joining:
- Gold invoice record
- PO header totals
- Vendor master attributes
- AI extraction outputs

It returns a set of named checks (PASS/WARN/FAIL) and a recommendation (APPROVE/HOLD/REJECT). This is deterministic logic implemented in the backend (not an LLM).

**Databricks products involved**
- Databricks SQL Warehouse (joins across curated tables)
- Unity Catalog governance for controlled access to underlying data

### 3) LLM-generated tab summaries
The app can generate a short “glance card” summary per tab by:
- Running a small “signals” SQL query per domain
- Calling an LLM via a **served model endpoint**
- Enforcing a strict output contract (3–4 bullets, formatting rules)

**Databricks products involved**
- Databricks Model Serving (served endpoint invocation)
- Databricks SQL Warehouse (signal queries)

### 4) Multi-agent conversational analytics (Supervisor + tools)
The chat experience is routed through a **multi-agent supervisor** served behind a Databricks serving endpoint. The supervisor returns a final formatted answer; intermediate tool calls (e.g., Genie) are not streamed directly to the UI in this implementation.

**Important repo constraint**
- The repo indicates the **supervisor endpoint** and **Genie space** are **manual** to provision (not deployable via Asset Bundles here).

**Databricks products involved**
- Model Serving (supervisor endpoint)
- Genie (as a tool the supervisor can call)
- Lakebase (chat session memory)

---

## Escalation & alerting (Databricks SQL Alerts V2)

From the AP Operations UI, users can escalate selected exception types. The backend:
1. Builds a SQL query summarizing selected exception categories.
2. Ensures a single persistent SQL Alert exists (found by display name).
3. Updates the alert query/schedule as needed.
4. Unpauses the schedule so Databricks evaluates and sends email within ~60 seconds.
5. Re-pauses the alert after a short delay.

**Databricks products involved**
- Databricks SQL Alerts (Alerts V2)
- Databricks SQL Warehouse (alert execution)

**What is configurable**
- Recipient email is configured server-side via an environment variable (not entered in the UI).

---

## Deployment model (Databricks Asset Bundles + manual steps)

### Bundle-managed components (automated)
Deployed via Databricks Asset Bundles:
- **DLT pipeline** (serverless, Photon)
- **Setup job** (data generation → DLT → Gold → AI processing)
- **Teardown job** (drops demo data and destroys resources)
- **Databricks App** (backend + frontend)

### Manual components (explicitly not bundle-deployable in this repo)
Per the repo documentation, these must be created manually:
- **Lakebase instance** (the app can attach to it, but the instance is created out-of-band)
- **Genie space** (created/configured via notebooks/UI)
- **Multi-agent supervisor endpoint** (AgentBricks / MAS-style endpoint)
- **Vector Search**: explicitly stated as **not used** by this demo

---

## End-to-end data flow (step-by-step)

1. **Synthetic data generation**
   - A setup notebook/job generates ERP-like datasets and invoice documents.

2. **Bronze/Silver pipeline**
   - DLT ingests raw data into Bronze and transforms into Silver.
   - DLT expectations enforce quality and quarantine invalid records.

3. **Gold transformations**
   - Separate notebook steps build Gold facts/dimensions and reconciliation views.

4. **AI invoice extraction**
   - AI Functions parse documents and extract structured fields into Silver (and/or enrich downstream tables).

5. **Serving to consumers**
   - The Databricks App reads KPIs and operational queues from Gold via SQL Warehouse.
   - SSE streams simulate/emit operational events based on real table rows.
   - Genie enables NLQ over curated Gold tables.
   - Multi-agent chat routes questions (via supervisor endpoint) and persists session history to Lakebase.

6. **Operational write-back**
   - Approvals, call logs, and chat history are written to Lakebase (or in-memory fallback).

7. **Escalation**
   - AP exception escalation triggers Databricks SQL Alerts to notify stakeholders.

---

## Prerequisites

### Workspace & permissions
- A Databricks workspace with:
  - Unity Catalog enabled and permissions to create schemas/tables in a chosen `{catalog}.{schema}`.
  - Permission to create and run DLT pipelines and Jobs.
  - Permission to deploy Databricks Apps.
  - Permission to use a SQL Warehouse (existing warehouse ID required).

### Compute / services
- **SQL Warehouse**: an existing warehouse ID is required for the app (and Genie).
- **DLT**: serverless DLT capability available in the workspace/region.
- **Model Serving**:
  - Access to invoke served endpoints for:
    - LLM summarization endpoint used by the summary card feature.
    - Multi-agent supervisor endpoint (manual to create).
- **Lakebase** (optional but recommended):
  - If not configured, the app runs with in-memory operational state (chat history, approvals, call logs won’t persist across restarts).

### Manual provisioning required (per repo)
- Create a Lakebase instance (if persistence is desired).
- Create/configure a Genie space and capture its ID.
- Create the multi-agent supervisor endpoint and capture its name/identifier.

### Configuration placeholders
Avoid hardcoding; use placeholders such as:
- `{catalog}` / `{schema}`
- `{warehouse_id}`
- `{lakebase_instance_name}`
- `{genie_space_id}`
- `{supervisor_endpoint_name}`

---

## What is *not* implemented / not used

- **Vector Search**: explicitly documented as *not used* in this demo.
- **Bundle-based provisioning** for Genie spaces, Lakebase instances, and the multi-agent supervisor endpoint: explicitly documented as not supported in this repo’s deployment automation.

---

## Suggested demo framing (Databricks use cases)

- **Finance data foundation**: unify ERP extracts + documents into a governed lakehouse (Unity Catalog + Delta).
- **Continuous controls & data quality**: enforce finance rules early (DLT expectations + quarantine).
- **Operational finance workbench**: real-time AP/AR/GL operations in a Databricks App (SSE + SQL Warehouse).
- **Touchless processing & exception management**: 3-way match classification + AI extraction + credibility checks.
- **Conversational analytics**: Genie for NLQ over curated Gold tables; multi-agent routing for domain-aware answers.
- **Operational write-back**: approvals, call logs, and chat memory stored in Lakebase for auditability and continuity.
- **Escalation automation**: SQL Alerts for exception-driven notifications.

---