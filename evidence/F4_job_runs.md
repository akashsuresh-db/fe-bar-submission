# F4 — Setup job runs

Job `[dev akash_s] cfo-fna-control-tower-setup-dev` (job id 696265687437193) on `fevm-akash-fevm-ts.cloud.databricks.com`.

Runs 3, 4 and 5 succeeded consecutively. Runs 4 and 5 ran the final pipeline code (including the GSTIN format guardrail) and were started by `setup/setup.sh`; between them only notebook 10 changed (the app's Postgres schema and a read grant on the synced queue). Runs 1 and 2 failed on defects found during testing, all fixed (see `RUN_LOG.md`).

| Run | Run id | Result | Start | Duration (min) |
|---|---|---|---|---|
| Run 1 (first attempt, before fixes found in testing) | 855788905315681 | FAILED | 2026-10-29 11:14:13 UTC | 11.1 |
| Run 2 | 865733328998014 | FAILED | 2026-10-29 11:28:50 UTC | 11.2 |
| Run 3 | 48029228378903 | SUCCESS | 2026-10-29 11:41:16 UTC | 12.5 |
| Run 4 (setup.sh) | 845044182389465 | SUCCESS | 2026-10-29 11:56:13 UTC | 9.7 |
| Run 5 (setup.sh) | 687143161761498 | SUCCESS | 2026-10-29 12:13:23 UTC | 9.4 |

## Run 1 (first attempt, before fixes found in testing) — 855788905315681

| Task | Result | Duration (min) | Message |
|---|---|---|---|
| reset_landing | SUCCESS | 0.5 |  |
| generate_data | SUCCESS | 1.2 |  |
| generate_pdf_invoices | SUCCESS | 1.7 |  |
| governance_pre | SUCCESS | 0.3 |  |
| run_pipeline | SUCCESS | 4.9 |  |
| ai_extraction_eval | SUCCESS | 0.9 |  |
| governance_post | FAILED | 1.2 | Workload failed, see run output for details |
| lakebase_sync | FAILED | 0.7 | The Python process exited unexpectedly with an abort signal (SIGABRT).
Please contact Databricks support and provide the trace ID: 747464605 |
| lakebase_sync | SUCCESS | 0.9 |  |
| governance_post | FAILED | 1.1 | Workload failed, see run output for details |
| genie_space | UPSTREAM_FAILED | 0.0 | An upstream task failed. |

## Run 2 — 865733328998014

| Task | Result | Duration (min) | Message |
|---|---|---|---|
| reset_landing | SUCCESS | 2.1 |  |
| generate_data | SUCCESS | 1.7 |  |
| generate_pdf_invoices | SUCCESS | 0.9 |  |
| governance_pre | SUCCESS | 0.3 |  |
| run_pipeline | SUCCESS | 4.9 |  |
| ai_extraction_eval | SUCCESS | 0.9 |  |
| governance_post | FAILED | 1.3 | Workload failed, see run output for details |
| lakebase_sync | SUCCESS | 0.7 |  |
| genie_space | UPSTREAM_FAILED | 0.0 | An upstream task failed. |

## Run 3 — 48029228378903

| Task | Result | Duration (min) | Message |
|---|---|---|---|
| reset_landing | SUCCESS | 2.0 |  |
| generate_data | SUCCESS | 1.8 |  |
| generate_pdf_invoices | SUCCESS | 1.8 |  |
| governance_pre | SUCCESS | 0.3 |  |
| run_pipeline | SUCCESS | 4.9 |  |
| ai_extraction_eval | SUCCESS | 1.0 |  |
| governance_post | SUCCESS | 1.4 |  |
| lakebase_sync | SUCCESS | 0.6 |  |
| genie_space | SUCCESS | 0.2 |  |

## Run 4 (setup.sh) — 845044182389465

| Task | Result | Duration (min) | Message |
|---|---|---|---|
| reset_landing | SUCCESS | 1.4 |  |
| generate_data | SUCCESS | 0.7 |  |
| generate_pdf_invoices | SUCCESS | 0.7 |  |
| governance_pre | SUCCESS | 0.3 |  |
| run_pipeline | SUCCESS | 5.3 |  |
| ai_extraction_eval | SUCCESS | 0.9 |  |
| governance_post | SUCCESS | 1.1 |  |
| lakebase_sync | SUCCESS | 0.7 |  |
| genie_space | SUCCESS | 0.2 |  |

## Run 5 (setup.sh) — 687143161761498

| Task | Result | Duration (min) | Message |
|---|---|---|---|
| reset_landing | SUCCESS | 1.6 |  |
| generate_data | SUCCESS | 0.6 |  |
| generate_pdf_invoices | SUCCESS | 0.7 |  |
| governance_pre | SUCCESS | 0.3 |  |
| run_pipeline | SUCCESS | 4.9 |  |
| ai_extraction_eval | SUCCESS | 0.8 |  |
| governance_post | SUCCESS | 1.1 |  |
| lakebase_sync | SUCCESS | 0.8 |  |
| genie_space | SUCCESS | 0.2 |  |

Task outputs of run 5: `job_outputs.json`. Notebook exports with cell outputs: `job_runs/`.
