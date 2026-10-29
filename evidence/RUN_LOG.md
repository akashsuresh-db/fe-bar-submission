# Run log

| Item | Value |
|---|---|
| Date | 2026-10-29 |
| Workspace | `https://fevm-akash-fevm-ts.cloud.databricks.com` (AWS us-east-1, FEVM) |
| Bundle | `cfo-fna-ops-control-tower`, target `dev` |
| Catalog.schema | `akash_fevm_ts_catalog.finance_ops_control_tower` |
| SQL warehouse | `87c76aa3893e6472` |
| Setup job | `696265687437193`. Run 3 `48029228378903`, run 4 `845044182389465` and run 5 `687143161761498` all succeeded; runs 4 and 5 were started by `setup.sh`. |
| Pipeline | `b6b62b82-aef9-48fc-b74d-c1ca9d868a92` (serverless, full refresh per setup run) |
| Lakebase | Instance `fna-control-tower-db`, database `databricks_postgres`, synced table `finance_ops_control_tower.ap_exception_queue` |
| Genie space | `01f1d38f62131010a21422b74b92e9e6` ("Finance Operations Control Tower") |
| App | `cfo-fna-control-tower-dev`, deployment `01f1d39467ed1d5bbf01c08784c9f321`, `https://cfo-fna-control-tower-dev-7474646051057767.aws.databricksapps.com` |
| MLflow | Experiment `/Users/akash.s@databricks.com/fna_control_tower_ai_extraction_eval`, run `f6233b66d98c47d99e58cb7b938421bc` |

## Stage checklist

| Stage | Proof file | Pass? |
|---|---|---|
| Lakeflow ingest (2+ consecutive clean job runs) | `F4_job_runs.md`, `pipeline_event_log.md` | Yes: runs 3–5 succeeded; 36 expectations with pass/fail counts |
| Unity Catalog governance | `F8_governance.md`, `lineage.md` | Yes: row filter, 3 masks, 22 tagged tables, 11 PII columns; restricted read shows 109 UK invoices and masked values; 100 lineage edges |
| Lakebase operational serving and write-back | `lakebase.md`, `F5_wiring.md` | Yes: 407 queue rows synced; app approvals and call logs in Postgres and in UC `ops_*` |
| Gen AI (extraction and evaluation) | `ai_eval.md` | Yes: 100% field accuracy on 200 PDFs; tamper recall 3/3; 0 false positives |
| Genie Agent | `genie_transcripts.md` | Yes: 6 of 6 questions completed, with SQL and results; app chat routes to Genie |
| Databricks App (live, no mocks) | `app_api_responses.md`, `tests.md` | Yes: `demo_mode=false`, OBO reads; all endpoints 200; 48 backend and 80 frontend tests pass |
| Recon tied with explained items, trial balance balanced | `F1_recon.md` | Yes: AR ₹1.53 Cr and AP ₹0.80 Cr explained by 4 items, ₹0 unexplained; DR = CR in every period |

## Fix status

| Fix | Status | Note |
|---|---|---|
| F1 Recon and trial balance | Done | GL posted from sub-ledgers; 4 seeded reconciling items |
| F2 AI tamper control and MLflow eval | Done | Tax-inclusive total, GSTIN and PO checks; `release_blocked`; notebook 09. INV000033 is no longer a tampered invoice in the regenerated data; the tampered set is INV000128, INV000198 and INV000204 |
| F3 Pipeline reads and AI extraction in pipeline | Done | No `spark.table` in the pipeline; 00b, 00c and 05 removed |
| F4 Idempotent setup job | Done | Raw-volume-only generator, reset with re-raise, `full_refresh: true` |
| F5 Bundle wiring | Done | Lakebase instance and app in the bundle; Genie created by the job and passed back by `setup.sh`. The Agent Bricks supervisor was not created (optional) |
| F6 No silent mock data | Done | `DEMO_MODE` only when explicit; typed 503 and banner; `auto_matched` from receipts |
| F7 Coherent data | Done | GSTIN match 97.9%; average days outstanding 59; every exception type populated |
| F8 Governance and OBO | Done, with FEVM substitutes | Workspace-local groups, because UC grants to them fail (account groups needed); SP grants via `setup.sh` |
| F9 Chat SQL guard | Done | sqlglot, allow-list, LIMIT ≤ 100, user token |
| F10 Docs | Done | Stale docs removed; DEMO_FLOW regenerated from live numbers |
| F11 README | Done | Outcome first, trade-offs, AI workflow |
| F12 Evidence | Done | This folder |
| F13 Tests | Done | 48 backend, 80 frontend; the deployed-app browser spec is skipped (needs an Apps login session) |

## Defects found and fixed during deployment testing

| Run | Defect | Fix |
|---|---|---|
| 1 | psycopg2-binary aborts on import in serverless notebooks | psycopg v3 |
| 1 | Shared metastore governs the tag key `domain` | `fna_process` |
| 2 | Shared metastore also governs `project` | `fna_project`, `fna_pii` |
| 2 | PDF generator read the vendors CSV without `multiLine`: 60% of PDFs had no vendor block | `multiLine` and an assertion on the vendor join |
| 3 | `ai_extract` invented GSTINs for foreign vendors (accuracy 0.765) | GSTIN format guardrail (accuracy 1.0) |
| 4 | App role cannot create tables in Postgres `public` | App schema `fna_app`; read grant on the synced queue |
| — | App env values cannot be empty | `none` sentinel for optional ids |
| — | `/api/metrics/r2r` scalar-subquery error | Latest-period filter |
