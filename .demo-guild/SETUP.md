# Finance Operations Control Tower — Setup Guide

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture Summary](#2-architecture-summary)
3. [Prerequisites](#3-prerequisites)
4. [Repository Structure](#4-repository-structure)
5. [Step-by-Step Setup](#5-step-by-step-setup)
   - [5.1 Configure CLI Authentication](#51-configure-cli-authentication)
   - [5.2 Validate the Bundle](#52-validate-the-bundle)
   - [5.3 Deploy via the Setup Script](#53-deploy-via-the-setup-script)
   - [5.4 Manual Components (Post-Bundle)](#54-manual-components-post-bundle)
   - [5.5 Wire Environment Variables into the App](#55-wire-environment-variables-into-the-app)
6. [Data: Generation and Pipeline](#6-data-generation-and-pipeline)
   - [6.1 Synthetic Data Generation](#61-synthetic-data-generation)
   - [6.2 DLT Pipeline (Bronze → Silver)](#62-dlt-pipeline-bronze--silver)
   - [6.3 Gold Layer Notebooks](#63-gold-layer-notebooks)
   - [6.4 AI Invoice Processing](#64-ai-invoice-processing)
   - [6.5 Regenerating Data from Scratch](#65-regenerating-data-from-scratch)
7. [Running the Application](#7-running-the-application)
   - [7.1 Deployed App (Databricks Apps)](#71-deployed-app-databricks-apps)
   - [7.2 Local Development](#72-local-development)
8. [Bundle Variables Reference](#8-bundle-variables-reference)
9. [Teardown](#9-teardown)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Overview

The Finance Operations Control Tower is a production-grade, end-to-end Finance & Accounting demo on Databricks. It covers three core financial workflows:

| Workflow | Abbreviation | Key Capability |
|---|---|---|
| Procure-to-Pay | P2P | Automated 3-way matching, AI invoice extraction, AP exception management |
| Order-to-Cash | O2C | Real-time AR aging, collections prioritisation, DSO tracking |
| Record-to-Report | R2R | Continuous journal entry validation, live trial balance, sub-ledger ↔ GL reconciliation |

The demo is delivered as a **Databricks Asset Bundle** (DAB) that deploys a Delta Live Tables pipeline, a setup job, and a Databricks App (FastAPI + React). Several components — Genie space, Multi-Agent Supervisor endpoint, and Lakebase instance — require manual provisioning and are documented in [Section 5.4](#54-manual-components-post-bundle).

---

## 2. Architecture Summary

```
Raw CSV files + Invoice PDFs (UC Volume)
        │  Auto Loader
        ▼
BRONZE LAYER  (Delta Live Tables)
  Raw ingestion tables — vendors, customers, POs, invoices, journal entries
  DLT Expectations: drop nulls, validate formats
        │  DLT transformations + ai_parse_document / ai_extract
        ▼
SILVER LAYER  (Delta Live Tables)
  Cleansed, deduplicated, 3-way matched invoices
  AI-extracted invoice fields
  Quarantine tables for failed expectations
        │  Spark SQL Gold notebooks
        ▼
GOLD LAYER  (Delta Tables)
  P2P: vendor dimension, invoice facts, payment facts
  O2C: customer dimension, sales facts, collections facts
  R2R: GL facts, trial balance facts, sub-ledger ↔ GL recon view
        │                              │
        ▼                              ▼
Genie AI Analyst              Finance Operations App
(natural language queries)    (React + FastAPI on Databricks Apps)
        │                       AP / AR / GL tabs · SSE streaming
        └──────────┬────────────Lakebase (managed Postgres)
                   ▼            approvals · call logs · chat history
          Multi-Agent Supervisor
          (Claude via FMAPI, tool_use)
          routes to P2P / O2C / R2R Genie sub-agents
```

**Databricks products used:**

| Product | Role |
|---|---|
| Delta Live Tables (Serverless) | Bronze → Silver ingestion pipeline with data quality expectations |
| Unity Catalog | Governance, lineage, RBAC, UC Volumes for raw files |
| `ai_parse_document()` / `ai_extract()` | Built-in SQL functions for invoice OCR and field extraction |
| Databricks SQL (Serverless Warehouse) | Gold layer queries, app metrics, Genie |
| Genie | Natural-language analytics over Gold tables |
| Databricks Apps | Serverless hosting for the FastAPI + React application |
| Lakebase (managed Postgres) | Operational state: AP approvals, AR call logs, chat history |
| Foundation Model API (Claude) | Multi-agent supervisor routing; LLM-generated tab summaries |
| Databricks SQL Alerts V2 | AP exception escalation via email |

---

## 3. Prerequisites

| Requirement | Notes |
|---|---|
| Databricks workspace (Azure or AWS) | Serverless compute must be enabled |
| Databricks CLI v0.200+ | `databricks --version` to confirm |
| CLI profile or `DATABRICKS_HOST` + `DATABRICKS_TOKEN` env vars | Used by the bundle and setup script |
| An existing **Serverless SQL Warehouse** | Note its ID — required as a bundle variable |
| Unity Catalog enabled | The bundle creates a catalog and schema |
| Python 3.10+ (local, for frontend build only) | Only needed for local dev; not required for deployed setup |
| Node.js 20+ and npm (local, for frontend build only) | Only needed if rebuilding the React frontend locally |
| `uv` (optional) | Used to regenerate the pinned `requirements.txt` lockfile |

---

## 4. Repository Structure

```
.
├── databricks.yml              # Asset Bundle root — name, variables, targets
├── resources/
│   ├── pipelines.yml           # DLT (Spark Declarative) pipeline definition
│   ├── jobs.yml                # Setup job (data gen → DLT → Gold → AI) + teardown job
│   └── apps.yml                # Databricks App definition + resource bindings
├── setup/
│   ├── setup.sh                # Idempotent deploy + demo build script
│   ├── teardown.sh             # Drop catalog + destroy bundle resources
│   └── teardown_catalog.py     # Notebook run by the teardown job (DROP CATALOG CASCADE)
├── notebooks/
│   ├── 00_Setup_and_Data_Generation.py   # Synthetic data generator
│   ├── 00b_Export_Raw_CSV.py             # Export generated data to raw CSV files
│   ├── 01_DLT_Pipeline.py                # DLT Bronze + Silver definitions
│   ├── 01a_Generate_PDF_Invoices.py      # Generate PDF invoices into UC Volume
│   ├── 02_Gold_Layer_P2P.py              # P2P Gold tables
│   ├── 03_Gold_Layer_O2C.py              # O2C Gold tables
│   ├── 04_Gold_Layer_R2R.py              # R2R Gold tables + recon view
│   ├── 05_Invoice_AI_Processing.py       # ai_parse_document + ai_extract
│   ├── 06_Genie_Space_Setup.py           # Table descriptions + sample questions
│   ├── 07_Create_Genie_Space.py          # Creates the Genie space via SDK
│   ├── 08_Configure_Genie_Space.py       # Adds instructions + curated questions
│   ├── fins_01_data_generator.py         # Alternate data generator (used by DLT job)
│   ├── fins_02_dlt_pipeline.py           # Alternate DLT pipeline notebook
│   └── genie_instructions.md             # Genie space system instructions
├── app/
│   ├── app.yaml                # Databricks Apps config (env vars, resource bindings)
│   ├── requirements.txt        # Fully pinned Python dependencies (== versions)
│   ├── requirements.in         # Direct dependencies (source for lockfile)
│   ├── backend/
│   │   ├── main.py             # FastAPI app: metrics, SSE streams, chat, approvals
│   │   ├── chat.py             # Multi-agent supervisor (MAS endpoint integration)
│   │   ├── streams.py          # SSE generators for P2P / O2C / R2R event feeds
│   │   ├── db.py               # Delta SQL queries via databricks-sql-connector
│   │   ├── lakebase.py         # Lakebase (Postgres) operational state
│   │   ├── escalate.py         # Databricks SQL Alerts V2 escalation
│   │   ├── summary.py          # LLM-generated tab summary cards
│   │   ├── invoice_pdf.py      # ReportLab PDF generation
│   │   └── config.py           # Workspace host, token, catalog/schema config
│   └── frontend/
│       ├── src/
│       │   ├── App.tsx                   # Root: tab routing, user identity
│       │   └── components/
│       │       ├── APTab.tsx             # AP Operations tab
│       │       ├── ARTab.tsx             # AR Operations tab
│       │       ├── GLTab.tsx             # GL Operations tab
│       │       ├── AIChatPanel.tsx       # Multi-agent chat with session history
│       │       ├── AIvsERPCard.tsx       # Pre-approval credibility check panel
│       │       ├── GLReconCard.tsx       # Sub-ledger ↔ GL reconciliation card
│       │       ├── ExceptionDrawer.tsx   # Exception detail drawer
│       │       └── InvoiceDrawer.tsx     # Invoice viewer + PDF download
│       ├── package.json
│       └── vite.config.ts
├── sql/
│   └── gold_finance_kpis.sql   # Reference SQL for Gold KPI queries
├── enablement/
│   └── DEMO_SCRIPT.md          # Standalone ~15-minute presenter's guide
└── tests/
    ├── playwright.config.ts
    ├── test_backend.py
    ├── test_e2e_deployed.spec.ts
    └── test_frontend.spec.ts
```

---

## 5. Step-by-Step Setup

### 5.1 Configure CLI Authentication

The bundle does **not** hardcode the workspace host. Supply it at runtime via one of:

```bash
# Option A — environment variables
export DATABRICKS_HOST=https://{your-workspace}.cloud.databricks.com
export DATABRICKS_TOKEN={your-pat-or-sp-token}

# Option B — CLI profile (recommended for repeated use)
databricks configure --profile {your-profile-name}
# Then pass --profile {your-profile-name} to every bundle command
```

Verify connectivity:

```bash
databricks workspace list / --profile {your-profile-name}
```

### 5.2 Validate the Bundle

```bash
databricks bundle validate -t dev
# With a named profile:
databricks bundle validate -t dev --profile {your-profile-name}
```

A clean validation prints the resolved resource graph with no errors. If `warehouse_id` is blank you will see a warning — supply it in the next step.

### 5.3 Deploy via the Setup Script

The setup script is idempotent and safe to re-run. It:

1. Deploys all bundle resources (DLT pipeline, jobs, app).
2. Triggers the setup job, which runs the notebooks in order:
   - Data generation → raw CSV export → DLT pipeline run → Gold layer notebooks → AI invoice processing.

```bash
# Minimal invocation (warehouse_id is required)
./setup/setup.sh --var="warehouse_id={your-warehouse-id}"

# With a named CLI profile and custom catalog/schema
./setup/setup.sh \
  --profile {your-profile-name} \
  --var="warehouse_id={your-warehouse-id}" \
  --var="catalog={your-catalog}" \
  --var="schema={your-schema}"
```

> **Note:** The setup job runs serverless notebooks sequentially. Total runtime is approximately 15–25 minutes on a cold workspace (DLT pipeline start-up + Gold notebook execution). Monitor progress in the Databricks Jobs UI.

To deploy the bundle only (without running the setup job):

```bash
databricks bundle deploy -t dev --var="warehouse_id={your-warehouse-id}"
```

### 5.4 Manual Components (Post-Bundle)

The following components cannot be created by a DAB today. Provision them after the bundle deploy completes, then feed the resulting IDs back to the app.

#### A. Lakebase (managed Postgres) instance

The app uses Lakebase for operational state (AP approvals, AR call logs, chat history). If Lakebase is absent the app falls back to in-memory demo mode automatically.

```bash
# Create the instance (CLI)
databricks database create-database-instance \
  --json '{"name": "{your-lakebase-instance-name}", "capacity": "CU_1"}'

# Then create the application database inside it
# Default database name expected by the app: finance_ops_app
```

Pass the instance name to the bundle if you used a non-default name:

```bash
./setup/setup.sh \
  --var="warehouse_id={your-warehouse-id}" \
  --var="lakebase_instance_name={your-lakebase-instance-name}"
```

`PGHOST`, `PGUSER`, and `PGPASSWORD` are injected automatically by the `database` resource binding in `resources/apps.yml`. The app generates a fresh short-lived credential on every connection using the Databricks SDK.

#### B. Genie space

Three notebooks handle Genie space creation. Run them in order from the Databricks workspace UI or via the Jobs API, passing `catalog`, `schema`, and `warehouse_id` as notebook widgets/job parameters:

1. **Table descriptions and sample questions notebook** — enriches Gold table metadata.
2. **Genie space creation notebook** — creates the space via the Databricks SDK and prints the space ID.
3. **Genie space configuration notebook** — adds system instructions (from `notebooks/genie_instructions.md`) and curated questions. Requires the space ID from step 2 as a widget parameter.

After creation, note the Genie space ID for the next step.

#### C. Multi-Agent Supervisor (MAS / AgentBricks) endpoint

Create the supervisor endpoint in AgentBricks (Databricks UI → Mosaic AI → Agent Evaluation / AgentBricks). Attach the Genie space created above as a tool. Note the serving endpoint name.

#### D. Post-manual wiring checklist

| Asset | Where to set it | Variable / env var |
|---|---|---|
| SQL Warehouse | `resources/apps.yml` `sql_warehouse` resource binding | `warehouse_id` bundle var |
| Lakebase instance | `resources/apps.yml` `database` resource binding | `lakebase_instance_name` bundle var |
| Genie space ID | App environment variable | `GENIE_SPACE_ID` |
| MAS endpoint name | App environment variable | `MAS_ENDPOINT_NAME` |

### 5.5 Wire Environment Variables into the App

After provisioning the manual components, update the app's environment variables. The simplest approach is to edit `app/app.yaml` before deploying (or re-deploying) the app:

```yaml
# app/app.yaml (relevant env vars — fill in your values)
env:
  - name: GENIE_SPACE_ID
    value: "{your-genie-space-id}"
  - name: MAS_ENDPOINT_NAME
    value: "{your-mas-endpoint-name}"
  - name: DATABRICKS_CATALOG
    value: "{your-catalog}"
  - name: DATABRICKS_SCHEMA
    value: "{your-schema}"
  - name: LAKEBASE_INSTANCE_NAME
    value: "{your-lakebase-instance-name}"
```

Then redeploy the app resource only:

```bash
databricks bundle deploy -t dev --var="warehouse_id={your-warehouse-id}"
# The app picks up the new env vars on next start
databricks apps restart {your-app-name}
```

Optionally set the escalation email recipient (defaults to a placeholder):

```bash
# Set via Databricks App settings UI or as an additional env var:
ESCALATION_RECIPIENT={your-escalation-email}
```

---

## 6. Data: Generation and Pipeline

### 6.1 Synthetic Data Generation

The data generation notebook creates a realistic synthetic Finance & Accounting dataset. It is run automatically by the setup job but can also be executed manually.

**What is generated (illustrative row counts):**

| Entity | Approx. Rows | Notes |
|---|---|---|
| Vendors | ~100 | With GSTIN, category, state |
| Customers | ~150 | 5 segments, credit limits |
| Purchase Orders | ~500 | 8 spend categories |
| P2P Invoices | ~577 | ~5% intentional duplicates |
| Journal Entries | ~2,000 | 50 GL accounts |
| Raw Invoice Documents | ~200 | Text-format TAX INVOICE files |

The generator uses deterministic seeds so the same demo runs identically on every execution. Approximately 3% of PDF invoices are deterministically corrupted by a small amount (5–15%) to ensure the `EXTRACTION_MISMATCH` exception type fires reliably during demos.

A second notebook exports the generated Delta tables to raw CSV files in a UC Volume path, simulating ERP file drops that Auto Loader ingests.

A third notebook generates PDF invoice files (using ReportLab) and writes them to a UC Volume, making them available for `ai_parse_document()` processing and for the app's PDF viewer endpoint.

### 6.2 DLT Pipeline (Bronze → Silver)

The DLT pipeline notebook defines all Bronze and Silver tables using the Spark Declarative (DLT) API. It is referenced by the bundle pipeline resource (`resources/pipelines.yml`) and runs serverlessly.

**Bronze tables** ingest from raw CSV files and UC Volume documents via Auto Loader.

**Silver tables** apply:
- Deduplication (invoice-level)
- 3-way match logic: PO ↔ Invoice ↔ GRN → `match_status` column with values `THREE_WAY_MATCHED`, `TWO_WAY_MATCHED`, `AMOUNT_MISMATCH`, `NO_PO_REFERENCE`, `EXTRACTION_MISMATCH`
- AI extraction: `ai_parse_document()` + `ai_extract()` on raw invoice documents

**DLT Expectations (data quality contracts):**

| Table | Expectation | On Failure |
|---|---|---|
| Bronze P2P invoices | `valid_amount`: amount > 0 | DROP |
| Bronze P2P invoices | `has_vendor`: vendor_id IS NOT NULL | DROP |
| Bronze journal entries | `balanced_entry`: abs(debit − credit) < 0.01 | QUARANTINE → exceptions table |
| Silver P2P invoices | `no_future_invoices`: invoice_date ≤ today | WARN |
| Silver P2P invoices | `valid_match_status`: status IN (valid set) | DROP |

Failed records that are quarantined land in a dedicated exceptions table, providing a SOX-ready audit trail.

### 6.3 Gold Layer Notebooks

Three notebooks build the business-ready Gold tables from Silver. They are run sequentially by the setup job after the DLT pipeline completes.

| Notebook | Tables Created |
|---|---|
| P2P Gold notebook | Vendor dimension, invoice facts (with aging buckets, DPO), payment facts |
| O2C Gold notebook | Customer dimension, sales facts, collections facts (with DSO, CEI) |
| R2R Gold notebook | GL facts, trial balance facts, sub-ledger ↔ GL reconciliation view |

The R2R notebook also creates `gold_recon_subledger_vs_gl` — a materialised view that proves the AP and AR sub-ledger totals tie to the corresponding GL trial balance accounts (delta = 0 when the loop is closed).

### 6.4 AI Invoice Processing

A dedicated notebook runs after the Gold layer. It uses two built-in Databricks SQL functions — no custom model deployment or API keys required:

```sql
-- Step 1: Parse raw invoice document (OCR + text extraction)
SELECT ai_parse_document(binary_content) AS parsed
FROM {catalog}.{schema}.bronze_raw_invoice_documents;

-- Step 2: Extract structured fields from parsed text
SELECT ai_extract(
  parsed:content::STRING,
  ARRAY[
    'invoice_number', 'vendor_name', 'vendor_gstin',
    'invoice_date', 'due_date', 'po_reference',
    'subtotal', 'cgst', 'sgst', 'total_amount',
    'bank_account_number', 'ifsc_code'
  ]
) AS extracted_fields
FROM {catalog}.{schema}.silver_parsed_invoices;
```

Extracted `total_amount` is reconciled against the ERP-sourced amount (±2% tolerance). Invoices where the extracted total differs by more than 2% are flagged as `EXTRACTION_MISMATCH` in the Silver layer.

### 6.5 Regenerating Data from Scratch

To regenerate all synthetic data and re-run the full pipeline:

```bash
# Option A — re-run the setup job (idempotent, drops and recreates all tables)
databricks jobs run-now {fna_setup_job_id}

# Option B — run notebooks manually in order from the workspace UI:
# 1. Data generation notebook
# 2. Raw CSV export notebook
# 3. PDF invoice generation notebook
# 4. Trigger DLT pipeline run (from Pipelines UI or CLI)
# 5. P2P Gold notebook
# 6. O2C Gold notebook
# 7. R2R Gold notebook
# 8. AI invoice processing notebook
```

To change the volume of synthetic data, pass widget parameters to the data generation notebook (e.g., number of vendors, invoices, journal entries). The downstream notebooks and pipeline are parameterised to pick up whatever the generator produces.

---

## 7. Running the Application

### 7.1 Deployed App (Databricks Apps)

After `databricks bundle deploy` completes and the manual components are wired up, the app is available at the URL shown in the Databricks Apps UI.

**Pre-demo health checks:**

```bash
# Confirm the app is healthy
curl https://{your-app-url}/api/health
# Expected: {"status":"healthy","app":"finance-operations"}

# Confirm the warehouse is warm and metrics load
curl -H "Authorization: Bearer {token}" https://{your-app-url}/api/metrics/p2p

# Confirm sub-ledger ↔ GL reconciliation
curl -H "Authorization: Bearer {token}" https://{your-app-url}/api/recon

# Confirm LLM summary generation
curl -H "Authorization: Bearer {token}" https://{your-app-url}/api/summary/P2P
```

If the app returns 502 or is unresponsive, restart it:

```bash
databricks apps restart {your-app-name}
# Allow ~90 seconds for the app container to start
```

The app authenticates users via Databricks OAuth SSO. The `x-forwarded-email` and `x-forwarded-access-token` headers are injected by the Databricks Apps proxy — no additional auth configuration is needed.

### 7.2 Local Development

For local development, the frontend proxies API calls to the backend running on `localhost:8000`.

**Backend:**

```bash
cd app

# Install dependencies (use uv or pip)
pip install -r requirements.txt

# Set required environment variables
export DATABRICKS_HOST=https://{your-workspace}.cloud.databricks.com
export DATABRICKS_TOKEN={your-pat}
export DATABRICKS_WAREHOUSE_ID={your-warehouse-id}
export DATABRICKS_CATALOG={your-catalog}
export DATABRICKS_SCHEMA={your-schema}
export GENIE_SPACE_ID={your-genie-space-id}
export MAS_ENDPOINT_NAME={your-mas-endpoint-name}
# Lakebase (optional — app falls back to in-memory if not set)
export PGHOST={your-lakebase-host}
export PGUSER={your-lakebase-user}
export PGPASSWORD={your-lakebase-password}
export PGDATABASE=finance_ops_app

# Start the backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**

```bash
cd app/frontend

npm install
npm run dev
# Vite dev server starts on http://localhost:5173
# API calls proxy to http://localhost:8000 (configured in vite.config.ts)
```

**Building the frontend for deployment:**

```bash
cd app/frontend
npm run build
# Copies compiled assets to app/backend/static/
cp -r dist/* ../backend/static/
```

The backend serves the compiled frontend from `backend/static/` as static files. The bundle deploy includes the pre-built static assets.

**Regenerating the Python dependency lockfile:**

```bash
cd app
uv pip compile requirements.in -o requirements.txt --python-version 3.11
```

---

## 8. Bundle Variables Reference

All variables can be overridden at deploy time with `--var="name=value"`.

| Variable | Default | Description |
|---|---|---|
| `catalog` | *(set in bundle)* | Unity Catalog catalog that holds all demo data |
| `schema` | *(set in bundle)* | Schema within the catalog |
| `warehouse_id` | `""` (required) | Existing Serverless SQL Warehouse ID |
| `lakebase_instance_name` | `finance-ops-db` | Lakebase managed Postgres instance name |

Example override:

```bash
databricks bundle deploy -t dev \
  --var="catalog={your-catalog}" \
  --var="schema={your-schema}" \
  --var="warehouse_id={your-warehouse-id}" \
  --var="lakebase_instance_name={your-lakebase-instance-name}"
```

---

## 9. Teardown

The teardown script drops the catalog (and all data within it) and destroys all bundle-managed resources:

```bash
./setup/teardown.sh
# With a named profile:
./setup/teardown.sh --profile {your-profile-name}
```

The teardown runs a job that executes a notebook to `DROP CATALOG {catalog} CASCADE`, then calls `databricks bundle destroy` to remove the DLT pipeline, jobs, and app.

> **Warning:** This is irreversible. All Delta tables, UC Volumes, and generated data in the catalog will be permanently deleted.

To destroy bundle resources only (without dropping the catalog):

```bash
databricks bundle destroy -t dev
```

---

## 10. Troubleshooting

### Warehouse is cold — app shows blank metrics

The app has a 120-second startup timeout for the warehouse connection. If the warehouse is in a stopped state when the app starts, it falls back to demo mode (empty metrics). Warm the warehouse by running any query in the SQL editor, then restart the app:

```bash
databricks apps restart {your-app-name}
```

### SSE streams show no data after clicking "Start Processing"

The app uses Server-Sent Events (SSE) for real-time invoice/collection/JE feeds. If the stream fails silently:

1. Open browser DevTools (F12) → **Network** tab.
2. Click "Start Processing" and look for a request to `/stream/p2p`.
3. Check the HTTP status:
   - `200` with no events → warehouse cold; wait and retry.
   - `401` → auth headers not injected by the proxy; verify the app is accessed via the Databricks Apps URL (not localhost).
   - `404` → backend not running; check app logs.
4. Check the **Console** tab for `SSE connection error:` messages — the app surfaces these as a red error banner in the UI.

### Lakebase not connecting — chat history not persisting

Check the diagnostics endpoint:

```bash
curl -H "Authorization: Bearer {token}" https://{your-app-url}/api/debug/status
```

The response includes `lakebase.demo_mode` (true = falling back to in-memory) and `lakebase.init_error` with the specific error. Common causes:

- `PGHOST` / `PGUSER` not set → Lakebase instance not attached to the app resource in `resources/apps.yml`.
- Token expired → the app auto-refreshes via `WorkspaceClient.database.generate_database_credential()`; if this fails, check that the app service principal has the `Can Use` permission on the Lakebase instance.

### Genie / MAS chat returns "No answer returned"

- Confirm `GENIE_SPACE_ID` and `MAS_ENDPOINT_NAME` are set in the app environment.
- Confirm the MAS endpoint is in `Ready` state in the Serving UI.
- Confirm the Genie space has the Gold tables attached and the instructions from `notebooks/genie_instructions.md` applied.
- Check the app logs for `HTTP 4xx` errors from the MAS endpoint invocation.

### DLT pipeline fails on `ai_parse_document`

`ai_parse_document()` requires the workspace to have Foundation Model API access enabled. Confirm in **Settings → Feature Flags** that FMAPI is enabled. The function also requires the raw invoice files to exist in the UC Volume before the pipeline runs — confirm the PDF generation notebook completed successfully.

### Bundle deploy fails with "warehouse_id is required"

The `warehouse_id` variable has no default and must be supplied explicitly:

```bash
databricks bundle deploy -t dev --var="warehouse_id={your-warehouse-id}"
```

Find your warehouse ID in **SQL → SQL Warehouses** in the Databricks UI, or via:

```bash
databricks warehouses list
```