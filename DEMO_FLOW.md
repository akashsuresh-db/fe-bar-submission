# Finance Operations Control Tower — Demo Flow

A 15-minute script in four acts, following one invoice from PDF to payment decision. It maps to deck slide 10.
Every figure below comes from the live build (`evidence/kpi_queries.md`, `evidence/F1_recon.md`). The data is
synthetic and deterministic, so a fresh `setup/setup.sh` run reproduces the same numbers.

| Asset | Where |
|---|---|
| App | `cfo-fna-control-tower-dev` (URL in `evidence/RUN_LOG.md`) |
| Pipeline | `[dev] cfo-fna-control-tower-dlt-dev` |
| Genie space | "Finance Operations Control Tower" |
| Tables | `<catalog>.<schema>` (this build: `akash_fevm_ts_catalog.finance_ops_control_tower`) |

The streams in the app are a **replay of governed Gold rows in posting-date order**. They show how the workbench
behaves as documents arrive; every row is a real row of the Gold tables.

---

## Act 1 · Accounts payable: the tampered invoice (5 minutes)

**1A. AP Operations tab, KPI strip.** 550 invoices; 189 touchless (**34.4%**). Touchless counts only clean
three-way matches that the AI control did not block.

> "A third of invoices flow through without a human today. The other two thirds are the cost and the risk."

**1B. Exception queue.** 407 invoices need attention (served from the Lakebase synced table). Point at the
exception types: 188 missing goods receipts, 98 amount mismatches, 72 without a PO, 27 duplicates, 16 critically
overdue, 3 missing GSTINs and **3 marked "Blocked: PDF ≠ ERP"**.

**1C. Open INV000198 (Dar, Raj and Wagle).** In the ERP it is a clean three-way match for ₹74.55 L, so a
rules-only process would pay it touchless. The PDF says **₹79.76 L**, 7% more.

> "AI Functions read every PDF inside the pipeline. When the document disagrees with the ERP on total, GSTIN or PO,
> the invoice is release-blocked. All three tampered PDFs in this data set were caught, with no clean invoice blocked."

**1D. Click "Verify before approve".** The release control fails and the recommendation is HOLD. Click "Show PDF" to
show the printed total. Approve or reject: the decision is written to Lakebase (`ap_approvals`) and copied into
Unity Catalog (`ops_ap_approvals`).

**1E. Duplicates.** 27 re-submitted invoices (₹26.77 Cr) were stopped before payment by matching vendor and invoice
number.

## Act 2 · Collections (2 minutes)

**2A. AR Operations tab.** Open AR is ₹17.37 Cr; average days outstanding is 59. The largest overdue balances are
Naidu-Gupta (₹1.21 Cr), Banerjee Inc (₹0.92 Cr) and Barad Group (₹0.82 Cr).

**2B. Log a call.** Pick a 90+ day customer, record a promise to pay with a date. The call log lands in Lakebase
(`ar_call_logs`) and in Unity Catalog through the write-back job.

## Act 3 · Close: the reconciliation (3 minutes)

**3A. GL Operations tab, reconciliation card.** For each control account the card shows the sub-ledger, the GL and
the explained items.

| Account | Sub-ledger | GL | Difference | Explained by |
|---|---|---|---|---|
| 1100 Accounts receivable | ₹17.37 Cr | ₹15.84 Cr | ₹1.53 Cr | 3 invoices whose journals are still in DRAFT |
| 2000 Accounts payable | ₹178.17 Cr | ₹177.37 Cr | ₹0.80 Cr | 1 invoice whose journal is still in DRAFT |

> "The GL is posted from the sub-ledgers. The difference is real, and every rupee of it is explained by a named
> document. Unexplained difference: zero. That is a tie-out an auditor accepts."

**3B. Show the trial balance.** Debits equal credits in every period. Five unbalanced manual journals were
quarantined by the pipeline and never reached the GL.

## Act 4 · Ask, govern, prove (5 minutes)

**4A. Finance AI chat (Genie Agent).** Ask, in turn:
1. "Which invoices were blocked because the PDF disagrees with the ERP?"
2. "Do AR and AP tie to the general ledger, and what explains any difference?"
3. "Which five customers have the largest overdue receivables?"

The chat pill shows the route (Genie) and that the query ran as the signed-in user. Transcripts:
`evidence/genie_transcripts.md`.

**4B. Governance.** In Catalog Explorer, open `gold_fact_invoices`: the row filter on `legal_entity` and the
`fna_process` tags. Open `silver_invoice_extractions`: bank account, IFSC and GSTIN are masked for anyone outside
`finance_controllers`. Because the app reads on behalf of the user, the same rules apply inside the app.

**4C. Pipeline and lineage.** Open the pipeline graph (bronze → silver → gold, including the AI extraction table) and
its Data Quality tab. Then show lineage from the raw volumes to `gold_ap_exception_queue` and the Lakebase synced
table.

**4D. AI evaluation.** Open the MLflow experiment `fna_control_tower_ai_extraction_eval`: per-field accuracy and tamper
recall for every build.

---

## Prep checklist

1. The SQL warehouse is running (the app shows a banner instead of numbers if it is not).
2. Open the app once to wake its compute; check `/api/debug/status` shows `demo_mode: false` and Lakebase connected.
3. Have the pipeline, Catalog Explorer and the MLflow experiment open in separate tabs.

## Backup SQL

```sql
-- Tampered invoices caught
SELECT invoice_id, vendor_name, invoice_total_inr, ai_extracted_amount, block_reason
FROM gold_fact_invoices WHERE release_blocked;

-- Reconciliation with explained items
SELECT account_code, subledger_amount, gl_amount, delta, reconciling_items_amount, unexplained_delta, tied
FROM gold_recon_subledger_vs_gl;
SELECT * FROM gold_recon_reconciling_items;

-- Trial balance balances (expect no rows)
SELECT period, SUM(CASE WHEN balance_type = 'DR' THEN closing_balance_inr ELSE -closing_balance_inr END) AS net
FROM gold_fact_trial_balance GROUP BY period HAVING ABS(net) > 1;

-- Touchless rate
SELECT ROUND(100 * AVG(CASE WHEN is_touchless THEN 1 ELSE 0 END), 1) AS touchless_pct FROM gold_fact_invoices;
```
