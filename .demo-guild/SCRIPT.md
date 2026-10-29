# Finance Operations Control Tower — Demo Script

## Overview

This document is a **~5-minute SA talk track** for the Finance Operations Control Tower demo. It is designed for a live walkthrough of the deployed Databricks App and supporting platform components. The narrative moves from business pain → live data → AI intelligence → platform proof, ending with a clear value statement.

---

## Pre-Demo Checklist

Before presenting, confirm the following are healthy:

| Check | What to Verify |
|---|---|
| SQL Warehouse | Running; queries return in under 2 seconds |
| App health endpoint | Returns `{"status":"healthy"}` |
| AR metrics endpoint | Returns a non-zero total outstanding value |
| GL reconciliation endpoint | Both AR and AP rows show `tied: true`, delta of zero |
| AI summary endpoint (P2P) | Returns 3–4 bullet points |
| Invoice verification endpoint | Returns a recommendation for a sample invoice ID |
| Browser session | Logged in via Databricks SSO; user avatar visible top-right |
| DLT pipeline | Most recent run shows `COMPLETED` state |

Keep a SQL editor tab open as a backup proof surface. Have the DLT pipeline graph open in a separate tab.

---

## The Talk Track

### Step 1 — Set the Stage (30 seconds)

**What to show:** The app landing page, AP Operations tab active, before clicking anything.

**What to say:**

> "Finance teams at mid-to-large enterprises run three critical workflows every day — Procure-to-Pay, Order-to-Cash, and Record-to-Report. The structural problem is the same across all three: data lives in ERP systems optimised for recording transactions, not for analysing them. AP clerks spend 60–70% of their time on manual matching. AR teams work from weekly batch exports. Month-end close takes 5–10 business days. And AI initiatives stall because the data foundation isn't there yet.
>
> What I'm going to show you in the next few minutes is all three of those workflows — resolved — running on a single Databricks Lakehouse. Everything you see is real data from a real Delta Live Tables pipeline. No mocks."

**Value to emphasise:** The pain is structural and universal. This is a platform answer, not a point solution.

---

### Step 2 — AP Operations: The Invoice Queue (90 seconds)

**What to show:** AP Operations tab. Point at the KPI strip, then click "Start Processing."

**What to say:**

> "Look at the summary card at the top — that's a live LLM reading the Gold table right now and synthesising what the AP lead needs to focus on first. It refreshes every time you switch tabs. No analyst built it.
>
> In the KPI strip: roughly a third of invoices are three-way matched — meaning purchase order, goods receipt, and invoice all reconcile within tolerance. Those go straight to payment with zero human touch. That's straight-through processing. The rest surface here as exceptions."

Click **Start Processing**. As invoices stream in:

> "Watch the green badges — those are auto-released. The pipeline classified every one of these at ingestion time using DLT Silver transformations: PO lookup, GRN check, 2% tolerance rule. That classification took seconds. The incumbent process takes 2–3 days.
>
> The orange and red badges are the exceptions — amount mismatches, missing PO references. Every one of them is here because a DLT Expectation fired. The same rule that drives the pipeline's data quality tab drives the exception type column the app reads. One source of truth."

Click a paperclipped exception row to open the exception drawer. Click **"Verify before approve"**.

> "Eight pre-approval checks in one click. Invoice total versus PO total. ERP vendor name versus what the AI extracted from the PDF. GSTIN match. Duplicate payment check across the last 90 days. Every line is auditable. If an AP clerk did this manually they'd open the ERP, the PDF, the PO, the vendor master, and the GRN — minimum five windows. Here it's one button, one panel, one decision."

**Value to emphasise:** 75–85% cost reduction per invoice. Touchless rate is live proof, not a slide claim.

---

### Step 3 — AR Operations and GL Close (60 seconds)

**What to show:** Switch to AR Operations tab, then GL Operations tab.

**What to say (AR):**

> "Switch to AR. The summary card now talks about overdue customers and collection priorities. The KPI strip shows total AR outstanding, DSO, and Collections Effectiveness Index — all live from the Gold collections table. This is the AR sub-ledger, updated continuously, not from a weekly ERP export.
>
> Click any overdue customer — you get a call logging modal. Promise-to-pay, dispute, voicemail, escalate. Whatever the collector logs goes into Lakebase — that's a managed Postgres instance running alongside the Lakehouse. Operational state, not analytical. The call list reorders tomorrow based on it."

Switch to GL Operations tab.

> "Now GL. This is the month-end close story. Look at the sub-ledger reconciliation card — AR and AP in the trial balance equal the sub-ledger totals to the rupee. Delta zero. Most finance shops have a reconciliation gap every period. We engineered it to zero by deriving GL balances directly from sub-ledger sums in the pipeline. Click 'Show Trial Balance' — nine accounts, correct sign convention, assets and expenses debit, liabilities and equity credit. The working-capital imbalance is visible, not hidden. That's what FP&A explains at close."

**Value to emphasise:** 50–70% faster month-end close. Continuous validation, not batch.

---

### Step 4 — Conversational AI (60 seconds)

**What to show:** The AI chat panel on the right side of the screen.

**What to say:**

> "The chat panel is a multi-agent supervisor. Ask it anything."

Type: **"Give me a working capital snapshot for the CFO right now."**

> "Watch the routing indicator — the supervisor is calling a Genie sub-agent, which queries the exact same Gold trial balance table the GL tab reads. Same row, same balance, same sign. The CFO and the AP clerk see the same truth."

Follow up: **"Which vendors have compliance below 80%?"**

> "That routes to the P2P sub-agent. Conversational SQL on governed data. No CSV export, no analyst hand-off. And because session history is persisted in Lakebase, I can ask 'those vendors' in the next question and it resolves correctly — multi-turn context across domain switches."

Open the session history drawer briefly.

> "Every conversation is stored. Any session can be resumed. Operational state in Lakebase, analytical state in Delta. Same platform, both serverless."

**Value to emphasise:** Natural language access to governed data. Finance users don't need SQL. The CFO gets the same number the AP clerk sees.

---

### Step 5 — Platform Proof (60 seconds)

**What to show:** Switch to the DLT pipeline graph tab.

**What to say:**

> "Here's the architecture proof. Bronze layer — Auto Loader reading from raw CSV files and invoice PDFs stored in Unity Catalog Volumes. Silver layer — this is where the 3-way match happens. Six DLT Expectations fire here: PO reference check, amount tolerance, GRN presence, GSTIN validation, overdue threshold, AI extraction reconciliation. Every failed record is quarantined, never reaches reporting. Gold layer — pre-aggregated P2P, O2C, and R2R models. Sub-second query time.
>
> Click the Data Quality tab in the pipeline. Those six predicates are the business rules. They drive both this tab and the exception_type column the app reads. SOX audit trail — done."

Switch back to the app. Open Unity Catalog lineage on the invoices Gold table if time permits.

> "Cell-level provenance. Any number you see in the app traces to a source row that traces to a source file in Unity Catalog. That's the AI-ready data foundation. The AI invoice extraction — `ai_parse_document` and `ai_extract` — are built-in SQL functions. No custom model, no API keys, no prompt engineering."

**Value to emphasise:** One platform — Delta Live Tables, Unity Catalog, Lakebase, Foundation Model APIs. No glue code between them.

---

### Step 6 — Close (30 seconds)

**What to show:** Return to the AP Operations tab with the KPI strip visible.

**What to say:**

> "Three workflows, one tab each. One platform underneath. The AP Manager saw the exception queue and the pre-approval panel. The AR lead saw the prioritised collections list with call logging. The CFO got a working capital snapshot from a chat message. Three personas, three tabs, designed to the workflow — not retrofitted to it.
>
> What we built is the data foundation and the operational layer. Touchless invoice routing, predictive payment timing, dispute root-cause analytics — those are a sprint away on the same foundation. A finance team can run this without an MLE."

---

## Recovery Scenarios

| Situation | Response |
|---|---|
| Warehouse cold, KPI cards blank | Keep talking through the architecture slide; pivot to the DLT pipeline graph |
| Invoice stream won't start | Demo the AI chat panel only — it has its own connection pool |
| App returns 502 | Restart the app via the Databricks CLI (`databricks apps start {app-name}`); takes ~90 seconds; talk through personas |
| Pipeline in error state | Prior Gold tables are still queryable; the reconciliation card reads materialised tables and will still render |

---

## Backup SQL Proofs

Paste these into a SQL editor tab as live evidence if needed. Replace `{catalog}` and `{schema}` with your deployment values.

```sql
-- 1. Sub-ledger ↔ GL tie-out (source of the reconciliation card)
SELECT * FROM {catalog}.{schema}.gold_recon_subledger_vs_gl;

-- 2. AR sub-ledger total — should match the AR Operations KPI strip
SELECT ROUND(SUM(balance_outstanding)/1e7, 2) AS ar_outstanding_cr
FROM {catalog}.{schema}.gold_fact_collections;

-- 3. Touchless rate — should match the AP Operations KPI strip
SELECT
  COUNT(*) AS total_invoices,
  SUM(CASE WHEN match_status = 'THREE_WAY_MATCHED' THEN 1 ELSE 0 END) AS touchless,
  ROUND(SUM(CASE WHEN match_status = 'THREE_WAY_MATCHED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS touchless_rate
FROM {catalog}.{schema}.gold_fact_invoices;

-- 4. DLT pipeline data quality events (most recent run)
SELECT event_type, details
FROM event_log('{your-pipeline-id}')
WHERE event_type = 'flow_progress'
ORDER BY timestamp DESC
LIMIT 1;

-- 5. AI-extracted invoice fields vs ERP (spot-check)
SELECT i.invoice_id, i.vendor_name, i.invoice_total_inr,
       x.extracted_vendor_name, x.extracted_total_amount, x.extracted_gstin
FROM {catalog}.{schema}.gold_fact_invoices i
JOIN {catalog}.{schema}.silver_invoice_extractions x ON i.invoice_id = x.invoice_id
LIMIT 10;
```

---

## Key Value Points by Persona

| Persona | What They Saw | Quantified Claim |
|---|---|---|
| **AP Manager** | Exception queue, verify-before-approve panel, touchless rate KPI | 75–85% cost reduction per invoice; 3-way match in seconds vs. 2–3 days |
| **AR Lead** | Prioritised collections list, call logging with PTP persistence | Continuous DSO visibility vs. weekly batch; collections state in Lakebase |
| **CFO / Controller** | Working capital snapshot from chat, sub-ledger ↔ GL reconciliation card | 50–70% faster month-end close; delta-zero reconciliation by design |
| **Data / IT** | DLT pipeline graph, Unity Catalog lineage, Databricks Asset Bundle deployment | Single platform — no glue code; SOX-ready data quality contracts |