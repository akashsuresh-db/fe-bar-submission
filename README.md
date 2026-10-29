# Finance Operations Control Tower on Databricks

**Customer (illustrative):** Meridian Advisory, a $1.2B professional-services firm whose India shared-services
centre runs Procure-to-Pay (P2P), Order-to-Cash (O2C) and Record-to-Report (R2R) for two legal entities
(`MERIDIAN-IN`, `MERIDIAN-UK`). All data in this repository is synthetic.

## 1. Outcome first

**The problem, in the buyer's KPIs.** Finance works from last week's ERP exports and spreadsheets. Invoices are
keyed and matched by hand (a touchless rate of about a third), duplicate and tampered invoices are found after
payment if at all, collections teams chase from stale aging lists, and the month-end tie-out of the sub-ledgers to
the general ledger takes days of manual reconciliation.

**The value case (estimated).** About **$2.8M a year** across four levers, plus **$16M of cash released** by a
5-day DSO reduction, about **11x** the estimated platform cost of $0.25M a year.

| Lever | Sizing basis (estimate) | Annual value |
|---|---|---|
| Working capital carry | A 5-day DSO cut on $1.2B revenue releases $16M, carried at 8% cost of capital | $1.3M |
| AP processing cost | 120K invoices a year, from $9.40 to $3.50 each at 70% touchless | $0.7M |
| Payment leakage blocked | Duplicates and overpayments at 0.1% of $480M vendor spend | $0.5M |
| Close effort | Three fewer close days a month for a 25-person finance team | $0.3M |
| **Total** | Platform cost estimated at $0.25M a year at pilot scale | **$2.8M (11x)** |

Invoice cost benchmark: Ardent Partners ePayables. All inputs are illustrative estimates for this customer profile.

**Proven on the build** (live results, `evidence/kpi_queries.md`):

| Result | Value |
|---|---|
| Touchless rate (clean three-way match, not release-blocked) | ⟦touchless⟧ |
| Duplicate invoices blocked before payment | ⟦dups⟧ |
| Value held for review in the exception queue | ⟦held⟧ |
| Tampered invoice PDFs caught by the AI control | ⟦tamper⟧ |
| AI extraction accuracy (total / PO / GSTIN) | ⟦accuracy⟧ |
| Sub-ledger to GL reconciliation | ⟦recon⟧ |
| Trial balance | Balances in every period (DR = CR) |

## 2. Architecture

```
raw_csv/ + raw_invoices/ (UC volumes)
   │  Auto Loader
   ▼
Lakeflow declarative pipeline ── bronze_* ── silver_* (expectations, dedup, ai_parse_document + ai_extract,
   │                                                   release_blocked) ── gold_* (facts, trial balance, recon)
   ▼
Unity Catalog: grants · row filter on legal_entity · masks on bank details/GSTIN · tags · lineage
   │
   ├── MLflow evaluation of the AI extraction (notebook 09)
   ├── Genie Agent over the governed tables (notebook 06)
   ├── Lakebase synced table ap_exception_queue (notebook 10) ◀── app reads the AP queue at OLTP latency
   ▼
Databricks App (FastAPI + React): KPIs, AP/AR/GL workbenches, Genie chat, approvals and call logs
   │  writes approvals, call logs, chat to Lakebase
   ▼
Lakebase → Unity Catalog write-back (ops_* tables), queryable by Genie
```

| Stage | Product | Main tables / objects | Evidence |
|---|---|---|---|
| Ingest | Lakeflow declarative pipeline, Auto Loader | `bronze_*` (17 streaming tables) | `evidence/F4_job_runs.md`, `evidence/pipeline_event_log.md` |
| Transform and quality | Lakeflow expectations, quarantine tables | `silver_p2p_invoices`, `silver_invoice_exceptions`, `silver_duplicate_invoices`, `silver_je_quarantine` | `evidence/pipeline_event_log.md` |
| Intelligence | AI Functions in the pipeline, MLflow | `silver_invoice_extractions`, `gold_ai_extraction_eval` | `evidence/ai_eval.md` |
| Business layer | Lakeflow materialized views | `gold_fact_*`, `gold_recon_*` | `evidence/F1_recon.md`, `evidence/kpi_queries.md` |
| Governance | Unity Catalog | grants, `rf_legal_entity`, `mask_bank_account`, `mask_gstin`, tags | `evidence/F8_governance.md`, `evidence/lineage.md` |
| Operational serving | Lakebase synced table and app tables | `ap_exception_queue`, `ap_approvals`, `ar_call_logs`, `chat_history` | `evidence/lakebase.md` |
| Natural language | Genie Agent, Conversation API | Genie space "Finance Operations Control Tower" | `evidence/genie_transcripts.md` |
| Application | Databricks Apps (on-behalf-of-user) | `cfo-fna-control-tower-dev` | `evidence/app_api_responses.md`, `evidence/tests.md` |

## 3. Decisions and trade-offs

| Decision | Chosen | Alternative | Why |
|---|---|---|---|
| AI extraction placement | `ai_parse_document` + `ai_extract` inside the pipeline as a streaming table | Separate notebook after the pipeline | One dependency graph, each PDF parsed exactly once, no double pipeline run; the cost is that the pipeline needs AI Functions on serverless |
| AI control | Block release when the PDF disagrees with the ERP on total (0.5%), GSTIN or PO | Flag only | A tampered invoice must never count as touchless; the touchless rate drops by the blocked invoices |
| Reconciliation | GL posted from sub-ledgers; delta explained by documented items | Override the GL with sub-ledger totals | A tie-out by construction proves nothing; an explained delta is what auditors accept |
| Data reads in the app | On-behalf-of-user authorization | App service principal | Row filters and masks apply per user; the service principal remains for background streams only |
| AP queue serving | Lakebase synced table from Gold | Direct warehouse queries | Millisecond reads for the queue the clerks work all day, with no warehouse warm-up |
| Lakebase to UC write-back | Copy job (`ops_*` tables) | Lakebase database catalog | The database catalog needs metastore `CREATE CATALOG`, unavailable on the FEVM workspace |
| Chat routing | Genie Conversation API; Agent Bricks supervisor optional | LLM-generated SQL | Genie answers from curated instructions and example SQL; the LLM fallback is guarded by a SQL parser and an allow-list |
| Groups | Workspace-local groups with `is_member()` | Account groups | FEVM cannot create account groups; production swaps in `is_account_group_member()` |
| Data | Deterministic synthetic generator (seed 42) | Customer data | Reproducible evidence; no customer data |

## 4. AI tools and workflow

- **Claude Code** was the build partner end to end: it read the FE BAR guidelines and the existing code, wrote the
  validation of the earlier build (circular recon, 0 of 3 tampered PDFs caught, failed setup runs), wrote the fix
  plan with acceptance tests, then implemented the fixes, deployed with the Databricks CLI, ran the job, queried the
  results and collected the evidence in `evidence/`.
- **Databricks AI Functions** (`ai_parse_document`, `ai_extract`) read the invoice PDFs inside the pipeline.
- **MLflow** records the extraction accuracy and tamper-detection metrics for every build.
- **Genie Agent** answers finance questions over the governed tables; the app chat uses the Genie Conversation API.
- **Foundation Model API (Claude)** writes the tab summaries and is the guarded last-resort chat fallback.

Representative prompts used during the build:

1. "Validate this build against the FE BAR guidelines; query the deployed tables to prove or disprove each claim."
2. "The recon delta is zero by construction. Generate journal entries from the sub-ledgers and seed a documented set
   of reconciling items so the recon shows a non-zero delta that is fully explained."
3. "Move AI extraction into the pipeline and block release when the PDF total, GSTIN or PO disagrees with the ERP;
   evaluate recall on the seeded tampered PDFs in MLflow."
4. "Collect text evidence for every acceptance test: SQL next to its result, job run exports, Genie transcripts."

## 5. Deploy, run and tear down

```bash
./setup/setup.sh -p <profile> --var="catalog=<catalog>" --var="schema=<schema>" --var="warehouse_id=<id>"
./setup/teardown.sh -p <profile> --var="catalog=<catalog>" --var="schema=<schema>" --var="warehouse_id=<id>"
```

`setup.sh` deploys the bundle, runs the setup job, wires the Genie space into the app, grants the app identity and
starts the app. [`MANUAL_DEPLOY.md`](MANUAL_DEPLOY.md) lists what each step creates and the platform constraints.
The demo script is [`DEMO_FLOW.md`](DEMO_FLOW.md); testing is described in [`docs/testing.md`](docs/testing.md).

| Path | Contents |
|---|---|
| `notebooks/00a_Reset_Schema.py` | Creates schema and volumes, clears the landing zone |
| `notebooks/00_Setup_and_Data_Generation.py` | Deterministic synthetic ERP extracts as raw CSV |
| `notebooks/01a_Generate_PDF_Invoices.py` | Invoice PDFs from the ERP extract, with seeded tampering |
| `notebooks/00d_Governance.py` | Groups, row filter, masks, tags, grants |
| `notebooks/01_DLT_Pipeline.py` | The declarative pipeline, bronze to gold, AI extraction |
| `notebooks/09_AI_Extraction_Evaluation.py` | MLflow evaluation |
| `notebooks/10_Lakebase_Sync.py` | Lakebase synced table and UC write-back |
| `notebooks/06_Genie_Space.py` | Genie space create/update |
| `app/` | FastAPI backend and React frontend |
| `resources/`, `databricks.yml` | The bundle |
| `evidence/` | Execution evidence |

## 6. Evidence index

| File | Proves |
|---|---|
| [`evidence/RUN_LOG.md`](evidence/RUN_LOG.md) | Workspace, run ids, pass/fail per stage |
| [`evidence/F4_job_runs.md`](evidence/F4_job_runs.md) | Two consecutive successful setup-job runs |
| [`evidence/job_outputs.json`](evidence/job_outputs.json) | Each task's `dbutils.notebook.exit` output |
| [`evidence/pipeline_event_log.md`](evidence/pipeline_event_log.md) | Expectation pass/fail counts per rule |
| [`evidence/F1_recon.md`](evidence/F1_recon.md) | Trial balance balances; recon tied with explained items |
| [`evidence/ai_eval.md`](evidence/ai_eval.md) | Extraction accuracy, tamper recall, MLflow run id |
| [`evidence/kpi_queries.md`](evidence/kpi_queries.md) | Every KPI with its SQL and result |
| [`evidence/F8_governance.md`](evidence/F8_governance.md) | Grants, masks, row filter, tags; masked vs clear reads |
| [`evidence/lineage.md`](evidence/lineage.md) | Lineage from raw volumes to gold and the synced table |
| [`evidence/lakebase.md`](evidence/lakebase.md) | Synced queue and app write-backs in Postgres and UC |
| [`evidence/genie_transcripts.md`](evidence/genie_transcripts.md) | Genie questions, generated SQL and answers |
| [`evidence/app_api_responses.md`](evidence/app_api_responses.md) | Live API responses from the deployed app |
| [`evidence/tests.md`](evidence/tests.md) | Unit and end-to-end test output |
