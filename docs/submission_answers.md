# FE BAR submission answers

## What is the business challenge you are solving?

Every finance organisation runs its cash cycle through three processes: procure-to-pay (paying vendors),
order-to-cash (collecting from customers) and record-to-report (tying both to the general ledger and closing the
books). In most companies the three run on separate exports, inboxes and spreadsheets, so the CFO sees the cash
position a week late and controls arrive after the money has moved. Meridian Advisory (an illustrative $1.2B
professional-services firm with India and UK entities) is a typical case:

- **Procure-to-pay: paying before checking.** The average AP team processes only 29% of invoices touchless
  ([Ardent Partners, State of ePayables 2025](https://tradeshift.com/wp-content/uploads/2025/07/Ardent-Partners-State-of-ePayables-2025-Tradeshift.pdf);
  best in class 51%); the rest cost about $9.40 each by hand
  ([Ardent Partners, AP Metrics that Matter 2025](https://www.datocms-assets.com/80283/1744404602-ardent-partners-ap-metrics-that-matter-in-2025-pagero-final.pdf)).
  Duplicate and tampered invoices are found after payment, because nothing compares the invoice PDF with the ERP
  record before the payment run.
- **Order-to-cash: collecting late.** Collectors chase customers from aging that is up to 7 days old, with no daily
  priority list, which keeps days sales outstanding high and cash tied up.
- **Record-to-report: closing by hand.** The AR and AP sub-ledgers are tied to the general ledger in spreadsheets over
  a 5–10 day month end, and unexplained differences reach the auditor.
- **No single view, uneven control.** The CFO cannot ask one question across vendors, customers and balances, and
  finance data is shared as files, so legal-entity restrictions and the masking of bank and tax identifiers depend on
  who receives the file.

The ask is one governed control tower over the whole cash cycle that any finance organisation can run: pay only what
is owed, collect faster, close with every difference explained, and let the CFO ask about any of it, with AI
surfacing only the exceptions that need a person.

## How does your Databricks solution address this challenge?

The Finance Operations Control Tower puts procure-to-pay, order-to-cash and record-to-report on one governed copy of
finance data, with a control built into each pillar:

- **One governed foundation.** Lakeflow Declarative Pipelines ingest the ERP extracts and invoice PDFs with Auto
  Loader, apply 36 expectations, quarantine duplicates and unbalanced journals and build the P2P, O2C and R2R gold
  layer. Unity Catalog applies a row filter by legal entity, masks on bank and tax fields, tags and lineage.
- **Procure-to-pay: pay right.** Clean three-way matches are paid touchless. AI Functions inside the pipeline
  (`ai_parse_document`, `ai_extract`) read every invoice PDF; when the PDF disagrees with the ERP on total, GSTIN or PO,
  the invoice is release-blocked. MLflow evaluates every build (100% field accuracy on 200 PDFs; 3 of 3 tampered
  invoices caught, no clean invoice blocked). Exceptions go to an AP queue served from Lakebase (a synced table) with
  the reason, and approvals are written back.
- **Order-to-cash: collect faster.** The app flags overdue receivables live and an AI summary (Foundation Model API)
  names the customers to chase first; collectors log calls and promise-to-pay dates in Lakebase, and a write-back job
  copies them into Unity Catalog.
- **Record-to-report: close with confidence.** The general ledger is posted from the sub-ledgers. The reconciliation
  shows AR and AP differences of $174K and $91K, each explained by named documents whose journals are still in
  draft ($0 unexplained), and the trial balance balances in every period.
- **The CFO asks anything.** A Genie Agent over 13 governed tables answers questions across vendors, customers and
  balances in the app chat. The app reads on behalf of the signed-in user, so a UK analyst sees only 109 UK invoices
  with masked bank details while a controller sees all 550.

AI never approves a payment; it blocks, ranks and explains, and a person decides. Everything deploys from one
Declarative Automation Bundle and `setup/setup.sh`; text evidence of each stage is in `evidence/`.

## What AI tools did you use, and what was your workflow?

- **Claude Code** was the build partner. It read the FE BAR guidelines and the existing build, validated it against
  the live workspace by querying the deployed tables, and found the critical defects (a reconciliation tied by
  construction, an unbalanced trial balance, 0 of 3 tampered PDFs caught, a setup job that had never completed). It
  wrote a fix plan with an acceptance test per defect, implemented the fixes in a local repository (with a parallel
  agent for the app), deployed to FEVM with the Databricks CLI, ran the job, queried the results and collected the
  evidence. Testing surfaced further defects that were fixed the same way: a tag-policy clash on a shared metastore,
  a Postgres driver crash on serverless, a CSV parsing bug that left vendor details off 60% of the PDFs, and the AI
  inventing GSTINs for foreign vendors (fixed with a format guardrail).
- **Databricks AI Functions** extract invoice fields; **MLflow** tracks extraction quality per build.
- **Genie Agent** provides governed natural-language analytics; the app chat calls the Genie Conversation API.
- **Foundation Model API (Claude)** writes the workbench summaries and is the guarded last-resort chat fallback
  (sqlglot parser, table allow-list, `LIMIT` ≤ 100, run as the user).

## What decisions and trade-offs did you make?

| Decision | Chosen | Alternative | Trade-off |
|---|---|---|---|
| AI extraction | In the pipeline, streaming table | Notebook after the pipeline | One graph and each PDF read once; requires AI Functions in serverless pipelines |
| AI control | Block release on mismatch | Flag only | Touchless rate counts only unblocked matches |
| AI output | GSTIN must match its format | Trust the model | Removed invented values (accuracy 0.765 → 1.0) |
| Reconciliation | GL from sub-ledgers, explained items | Override GL with sub-ledger totals | A real difference to explain, which is what auditors accept |
| App access | On-behalf-of-user | Service principal | Masks and filters per user; the SP is kept for background work |
| AP queue | Lakebase synced table | Warehouse queries | Millisecond reads; snapshot refresh after each build |
| Write-back to UC | Copy job | Lakebase database catalog | The catalog needs metastore `CREATE CATALOG`, not available on FEVM |
| Groups | Workspace-local, `is_member()` | Account groups | FEVM limitation; production uses `is_account_group_member()` |
| Ingestion | Auto Loader on extracts | Lakeflow Connect | Works on existing extracts now; Connect is the production step |

## What are the business outcomes and impact?

**Estimated value:** about $2.8M a year for the illustrative customer, about 11x an estimated $0.25M platform cost,
across all three pillars:

- **Order-to-cash:** $1.3M working-capital carry on $16M of cash released by a 5-day DSO reduction
- **Procure-to-pay:** $0.7M AP processing cost (120K invoices a year from $9.40 to $3.50 each at the 70% touchless
  pilot target, against a 29% industry average and 51% best in class) and $0.5M payment leakage blocked
- **Record-to-report:** $0.3M close effort from a daily tie-out instead of a 5–10 day month end

**Proven on the build (synthetic data, every figure traced to a query in `evidence/`; the build stores INR, shown here in US$ at 88 per dollar):**

- **Procure-to-pay:** 34.4% touchless (189 of 550) on a deliberately exception-heavy test set; 3 of 3 tampered
  invoices blocked, one of them (INV000198, +7%) otherwise payable touchless; 27 duplicates ($3.0M) stopped before
  payment; 407 exceptions routed with a reason
- **Order-to-cash:** $2.0M open across 37 customers, 59-day DSO, 88.9% collection effectiveness, overdue items
  flagged live and calls logged to Lakebase and Unity Catalog
- **Record-to-report:** sub-ledgers tied to the GL with every difference explained ($0 unexplained); trial balance
  balanced in every period; five unbalanced journals kept out of the GL
- **CFO view:** Genie answered 6 of 6 test questions across the three pillars, with per-user governance enforced in
  the app and in Genie

The proposed next step is a 10-week pilot on one legal entity across all three pillars, measured on touchless rate
(target 70%), days sales outstanding and tie-out time.
