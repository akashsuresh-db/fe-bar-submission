# Demo Script — Finance & Accounting Ops Control Tower

A self-contained, ~15-minute presenter's script any SA can run. It is **deck-independent**
(no slide numbers) and uses **placeholders** for environment-specific values — fill them in
from your deployment (`databricks bundle summary -t dev`) before presenting.

- **Audience:** Office of the CFO — Controllership, AP/AR leaders, FP&A, Finance IT
- **Duration:** ~15 min walkthrough + 5 min Q&A
- **Format:** live app + Databricks workspace (pipeline, Unity Catalog, Genie). No mocks.
- **Sub-industry:** Professional Services

> **Related assets:** high-level overview in [`../DEMO.md`](../DEMO.md); the buildathon
> slide-mapped variant in [`../DEMO_FLOW.md`](../DEMO_FLOW.md); deployment in
> [`../README.md`](../README.md) §0 and [`../MANUAL_DEPLOY.md`](../MANUAL_DEPLOY.md).

---

## 0. Fill these in before you present

| Placeholder | Where to get it | Your value |
|---|---|---|
| App URL | `databricks bundle summary -t dev` → app | `https://<your-app>.databricksapps.com` |
| Workspace URL | your profile / `DATABRICKS_HOST` | `https://<your-workspace>.cloud.databricks.com` |
| DLT pipeline | bundle summary → pipeline | `<your-pipeline-id>` |
| Genie space | `MANUAL_DEPLOY.md` step 2 | `<your-genie-space-id>` |
| SQL warehouse | bundle var `warehouse_id` | `<your-warehouse-id>` |
| Catalog · Schema | bundle vars | `fna_control_tower_catalog` · `finance_and_accounting` |

> **Numbers in this script are illustrative.** The demo runs on synthetic, deterministically
> generated data, so counts are stable run-to-run — but read the live values off the screen.

---

## 1. The one-sentence setup (before you touch anything)

> *"Finance runs on three loops — Procure-to-Pay, Order-to-Cash, and Record-to-Report —
> and every one of them leaks time to manual invoice handling, stale receivables, and a
> slow month-end close. Underneath, the data is fragmented, which is exactly what blocks
> AI. In the next twelve minutes I'll show all three loops resolved live on one Databricks
> platform — real data, a real Spark Declarative Pipeline, no glue code between the parts."*

Open two browser tabs: the **app** and the **DLT pipeline** (keep the pipeline tab hidden until Act 4).

---

## 2. Act 1 — The AP nightmare, solved (≈4 min)

**Story:** touchless invoice processing and pre-approval verification.

### 2A. Open the **AP Operations** tab
- Point at the **"Today's AP priorities" summary card** at the top; read one bullet aloud.
  > *"That summary is a foundation model reading the live gold table and telling an AP lead
  > what to look at first. It refreshes on tab switch — no analyst built it, no dashboard to maintain."*
- Point at the **KPI strip** (Total Invoices · 3-Way Matched · Exceptions · Touchless Rate).
  > *"Every invoice that went through with zero human touch is counted here. That touchless
  > rate is the number this scales — 70–85% at production volume."*

### 2B. Click **"Start Processing"** — invoices stream in

| Point at | Say |
|---|---|
| Green **3-Way Matched** badges | *"Auto-released to payment. The incumbent process takes 2–3 days; here it's a few seconds per invoice."* |
| The 📎 **paperclip** on some rows | *"That means the source PDF lives in a Unity Catalog Volume — the same byte image the AI read."* |
| Orange **Amount Mismatch** / red **No PO Reference** badges | *"Exceptions surface automatically, classified by the pipeline's business rules — not a hand-written CASE WHEN."* |

### 2C. Open an exception (search the queue for an **AMOUNT_MISMATCH** with a 📎)
1. The **exception drawer** opens — call out the **exception type + SLA clock**.
2. Click **"Verify before approve"** (shield icon).
3. The AI-vs-ERP card slides in with ~8 named credibility checks. Read 2–3 aloud —
   **Invoice ↔ PO total**, **ERP vendor ↔ PDF vendor**, **Duplicate-payment check** — then the
   **REJECT / HOLD / APPROVE** recommendation.
   > *"Eight pre-approval checks in one click, every line auditable. By hand this clerk would
   > open the ERP, the PDF, the PO, the vendor master, and the GRN — five windows. Here it's
   > one panel, one decision."*

### 2D. Click **"Show PDF"** on that invoice
- Show the footer: *Source: UC Volume · raw_invoices/INV…pdf*.
  > *"This is the exact byte image in Unity Catalog, fetched via the Files API — the same PDF
  > the AI extracted from, and the same one a CFO can pull during an audit. That's end-to-end
  > traceability."*

---

## 3. Act 2 — AR collections + GL close (≈3 min)

**Story:** prioritized receivables and a month-end close that ties out to zero.

### 3A. **AR Operations** tab
- Point at the summary card (overdue customers, top recovery candidates) and the KPIs
  (AR Outstanding · DSO · CEI · Overdue customers).
  > *"This is the AR sub-ledger — a governed gold table, not a weekly ERP export."*
- Click an **aging 90+** customer → the **call modal** (PTP / Dispute / Voicemail / Escalate).
  Pick **PTP**, set a date, submit.
  > *"That promise-to-pay just wrote to Lakebase — managed Postgres for operational state.
  > Tomorrow's call list reorders on it. Operational state and analytics on one platform."*

### 3B. **GL Operations** tab — the punchline
- Point at the **Sub-ledger ↔ GL reconciliation card**: AR and AP tie to the trial balance
  to the rupee, delta 0.
  > *"Most finance shops carry a delta here every period. We engineered it to zero by deriving
  > the GL balances directly from sub-ledger sums in the pipeline. Click in and it names the
  > source tables — `gold_fact_collections` and `gold_fact_invoices`."*
- Click **"Show Trial Balance"** — walk the sign convention (Assets/Expenses DR;
  Liabilities/Equity/Revenue CR).
  > *"The TB total is intentionally non-zero — it surfaces the working-capital pressure instead
  > of hiding it. That delta is exactly what FP&A explains at close."*
- Click **"Start JE Validation"** — journal entries stream; the close checklist shrinks.
  > *"Continuous validation, not month-end-only."*

---

## 4. Act 3 — Conversational AI (Genie + Multi-Agent Supervisor) (≈2 min)

**Story:** the CFO's single view of working capital, no analyst hand-off.

### 4A. Open the **Finance AI** panel and ask:
> **"Give me a working-capital snapshot for the CFO right now."**

The supervisor routes to Genie, which queries the same gold trial-balance table the GL tab reads.
  > *"Not an LLM guessing numbers — a multi-agent supervisor routing to Genie over governed
  > data. Same row, same balance, same sign the AP clerk sees."*

### 4B. Multi-turn follow-up:
> **"Which vendors have compliance below 80%?"**

Routes to the P2P sub-agent → `gold_dim_vendor`; the SQL accordion shows the query.
  > *"Conversational SQL on governed data. No CSV export, no analyst in the loop."*

### 4C. Open an earlier chat in the **session-history drawer** — it resumes with full context.
  > *"Chat history persists in Lakebase. Operational state in Postgres, analytical state in
  > Delta — both serverless, one platform."*

---

## 5. Act 4 — The architecture proof (≈3 min)

Switch to the **DLT pipeline** tab.

### 5A. The layered pipeline graph
- **Bronze** streams from `/raw_csv/` CSVs and `/raw_invoices/` PDFs via Auto Loader.
  *"Real ingestion — bronze reads files, not another Delta table."*
- **Silver** — `silver_p2p_invoices` is the heart: 3-way match + business-rule `@dlt.expect`s.
- **Gold** — AR/AP sub-ledgers, dimensions, and the trial balance derived from sub-ledgers.

### 5B. Click the **Data Quality** tab
- Show the business-rule expectations with live passed/failed counts.
  > *"These predicates ARE the business rules. They drive both the pipeline's data-quality tab
  > AND the exception-type column the AP queue reads — one source of truth, no drift."*

### 5C. **Unity Catalog → Lineage** on `gold_fact_invoices`
- Show the tree back to `/raw_csv/…` and `/raw_invoices/*.pdf`.
  > *"Cell-level provenance. Any number in the app traces to a source row, which traces to a
  > source file in Unity Catalog. That's the AI-ready data foundation."*

---

## 6. Act 5 — Business impact + close (≈2 min)

Back in the app (AP tab visible), tie the impact to what's on screen:

| Impact claim | What proves it live |
|---|---|
| 75–85% lower cost per invoice | The touchless-rate KPI |
| ~98% faster 3-way matching | `silver_p2p_invoices` classifies the full batch in seconds every cycle |
| 50–70% faster close | Live trial balance + sub-ledger↔GL recon → no manual reconciliation |

Personas:
> *"AP Manager saw the exceptions queue and Verify-before-approve. AR Lead saw prioritized
> collections with PTP logging. CFO/Controller saw the working-capital snapshot from chat.
> Three personas, three tabs, one platform — designed to the workflow, not retrofitted."*

**Close:**
> *"Three workflows, one tab each, one platform underneath — Spark Declarative Pipelines,
> Unity Catalog, Lakebase, Foundation Model APIs. We wrote no glue between them; they composed
> natively. A finance team can run this without an MLE. That's the controllership of tomorrow."*

Leave the app URL on screen → Q&A.

---

## 7. Pre-demo checklist (run 10 min before)

| Check | Where | Expected |
|---|---|---|
| Warehouse hot | SQL warehouse `<your-warehouse-id>` | RUNNING; queries < 1s |
| App healthy | `<app>/api/health` | `{"status":"healthy"}` |
| AR data live | `<app>/api/metrics/o2c` | non-zero `total_outstanding` |
| GL recon ties | `<app>/api/recon` | rows `tied: true`, `delta: 0` |
| AP summary | `<app>/api/summary/P2P` | 3–4 bullets |
| Verify endpoint | `<app>/api/verify-invoice/<invoice_id>` | a recommendation returns |
| Logged in | app top-right | avatar visible |
| Pipeline last run | DLT | `state: COMPLETED` |
| Genie configured | `<your-genie-space-id>` | instructions loaded (see `notebooks/genie_instructions.md`) |

**Rebuild from zero if needed:** `./setup/setup.sh --var="warehouse_id=<your-warehouse-id>"`
(idempotent; see README §0).

---

## 8. Recovery plan (if something breaks mid-demo)

- **Warehouse cold (queries > 10s):** keep narrating architecture; the summary cards show a
  "Generating…" skeleton. Pivot to the DLT pipeline tab.
- **Queue won't stream:** demo the AI panel only — it uses its own connection pool.
- **App 502:** restart via `databricks apps start <app-name>` (~90s); talk through architecture meanwhile.
- **Pipeline in error:** previously materialized gold tables are still queryable — the recon
  card keeps rendering. Do **not** trigger a refresh during the demo.

---

## 9. Backup proof — SQL snippets (paste into a SQL editor tab)

```sql
-- Sub-ledger <-> GL tie-out (the recon card's source)
SELECT * FROM fna_control_tower_catalog.finance_and_accounting.gold_recon_subledger_vs_gl;

-- AR sub-ledger total = AR Operations headline
SELECT ROUND(SUM(balance_outstanding)/1e7, 2) AS ar_outstanding_cr
FROM fna_control_tower_catalog.finance_and_accounting.gold_fact_collections;

-- The PDF in the UC Volume = the PDF the app serves
SELECT md5(content) FROM read_files(
  '/Volumes/fna_control_tower_catalog/finance_and_accounting/raw_invoices',
  format => 'binaryFile')
WHERE path LIKE '%INV000011.pdf';
```

*(All identifiers above are synthetic; replace catalog/schema if you deployed with different
bundle variables.)*

---

## 10. Component → where it lives (for follow-up questions)

| Component | Built thing |
|---|---|
| Bronze→Silver→Gold pipeline | `notebooks/01_DLT_Pipeline.py` + `@dlt.expect` predicates |
| AI invoice extraction | `notebooks/05_Invoice_AI_Processing.py` (`ai_parse_document` + `ai_extract`) |
| 3-way match | `silver_p2p_invoices.match_status` (PO + GRN) |
| Real-time AP / AR / GL screens | `app/frontend/src/components/{APTab,ARTab,GLTab}.tsx` + SSE streams |
| Conversational AI | MAS supervisor endpoint → Genie space (`MANUAL_DEPLOY.md`) |
| Lakebase state | `app/backend/lakebase.py` (approvals, call logs, chat history) |
| Deployment | `databricks.yml` + `resources/` + `setup/` (README §0) |

— end —
