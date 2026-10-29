# FE BAR submission answers

## How does your Databricks solution address this challenge?

Meridian Advisory (an illustrative $1.2B professional-services firm) runs P2P, O2C and R2R for two legal entities from
weekly ERP exports and spreadsheets: about a third of invoices are processed touchless, duplicates and tampered
invoices are found after payment, collections work from stale aging, and the month-end tie-out of sub-ledgers to the
general ledger is manual. The Finance Operations Control Tower replaces this with one governed flow:

- **Lakeflow Declarative Pipelines** ingest the ERP extracts and invoice PDFs with Auto Loader, apply 36 expectations,
  quarantine duplicates and unbalanced journals, run the three-way match and build the P2P, O2C and R2R gold layer.
- **AI Functions inside the pipeline** (`ai_parse_document`, `ai_extract`) read every invoice PDF. When the PDF
  disagrees with the ERP on total, GSTIN or PO, the invoice is release-blocked and can never be paid touchless.
  **MLflow** evaluates every build: 100% field accuracy on 200 PDFs and 3 of 3 tampered invoices caught, with no clean
  invoice blocked.
- The **general ledger is posted from the sub-ledgers**; the reconciliation shows AR and AP differences of ₹1.53 Cr
  and ₹0.80 Cr, each fully explained by named documents whose journals are still in draft (₹0 unexplained), and the
  trial balance balances in every period.
- **Unity Catalog** applies a row filter by legal entity, masks on bank and tax fields, tags and lineage; the
  **Databricks App** reads on behalf of the signed-in user, so a UK analyst sees only 109 UK invoices with masked bank
  details while a controller sees all 550.
- **Lakebase** serves the AP exception queue (a synced table from Gold) and stores approvals, call logs and chat; a
  write-back job copies them into Unity Catalog. The **Genie Agent** answers finance questions in the app chat.

Everything deploys from one Asset Bundle and `setup/setup.sh`; text evidence of each stage is in `evidence/`.

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

**Estimated value:** about $2.8M a year for the illustrative customer, about 11x an estimated $0.25M platform cost:

- $1.3M working-capital carry on $16M of cash released by a 5-day DSO reduction
- $0.7M AP processing cost (120K invoices from $9.40 to $3.50 each at 70% touchless)
- $0.5M payment leakage blocked
- $0.3M close effort

**Proven on the build (synthetic data):**

- 34.4% touchless today (189 of 550 invoices)
- 27 duplicates (₹26.8 Cr) stopped before payment
- 3 of 3 tampered invoices blocked; one of them (INV000198, +7%) would otherwise have been paid touchless
- 407 exceptions routed with a reason
- Sub-ledgers tied to the GL with every difference explained
- Per-user governance enforced in the app and Genie

The proposed next step is a 10-week, AP-first pilot on one entity.
