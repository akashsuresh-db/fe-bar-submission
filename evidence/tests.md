# Tests

_Run 2026-10-29 13:05 UTC from the local repository._

## Backend unit tests (pytest, mocked workspace) — 48 passed

`PYTEST=<venv>/bin/pytest ./tests/run_tests.sh backend`

Covers the chat SQL guard (DDL, DML, multiple statements, off-list tables, LIMIT clamp), touchless excluding
release-blocked invoices, recon tied logic, Genie route selection, demo-mode typed errors and the debug status shape.

```
../tests/test_backend.py::test_health PASSED                             [  2%]
../tests/test_backend.py::test_me_reads_forwarded_identity PASSED        [  4%]
../tests/test_backend.py::TestSqlGuard::test_rejects_ddl[DROP TABLE gold_fact_invoices] PASSED [  6%]
../tests/test_backend.py::TestSqlGuard::test_rejects_ddl[CREATE TABLE gold_x AS SELECT 1] PASSED [  8%]
../tests/test_backend.py::TestSqlGuard::test_rejects_ddl[ALTER TABLE gold_fact_gl ADD COLUMN x INT] PASSED [ 10%]
../tests/test_backend.py::TestSqlGuard::test_rejects_ddl[GRANT SELECT ON gold_fact_gl TO `someone`] PASSED [ 12%]
../tests/test_backend.py::TestSqlGuard::test_rejects_dml[DELETE FROM gold_fact_invoices] PASSED [ 14%]
../tests/test_backend.py::TestSqlGuard::test_rejects_dml[UPDATE gold_fact_invoices SET release_blocked = false] PASSED [ 16%]
../tests/test_backend.py::TestSqlGuard::test_rejects_dml[INSERT INTO gold_fact_gl SELECT * FROM gold_fact_gl] PASSED [ 18%]
../tests/test_backend.py::TestSqlGuard::test_rejects_dml[MERGE INTO gold_fact_gl t USING gold_fact_gl s ON t.je_id = s.je_id WHEN MATCHED THEN DELETE] PASSED [ 20%]
../tests/test_backend.py::TestSqlGuard::test_rejects_multiple_statements PASSED [ 22%]
../tests/test_backend.py::TestSqlGuard::test_rejects_off_list_tables[SELECT * FROM bronze_vendors] PASSED [ 25%]
../tests/test_backend.py::TestSqlGuard::test_rejects_off_list_tables[SELECT * FROM silver_invoice_extractions] PASSED [ 27%]
../tests/test_backend.py::TestSqlGuard::test_rejects_off_list_tables[SELECT * FROM system.access.audit] PASSED [ 29%]
../tests/test_backend.py::TestSqlGuard::test_rejects_off_list_tables[SELECT * FROM gold_fact_invoices WHERE vendor_id IN (SELECT vendor_id FROM bronze_vendors)] PASSED [ 31%]
../tests/test_backend.py::TestSqlGuard::test_rejects_other_schema PASSED [ 33%]
../tests/test_backend.py::TestSqlGuard::test_adds_limit_and_qualifies PASSED [ 35%]
../tests/test_backend.py::TestSqlGuard::test_clamps_large_limit PASSED   [ 37%]
../tests/test_backend.py::TestSqlGuard::test_keeps_small_limit_and_ctes PASSED [ 39%]
../tests/test_backend.py::TestSqlGuard::test_allows_exceptions_and_eval_tables PASSED [ 41%]
../tests/test_backend.py::TestSqlGuard::test_sql_agent_refuses_generated_ddl PASSED [ 43%]
../tests/test_backend.py::TestTouchless::test_touchless_query_excludes_release_blocked PASSED [ 45%]
../tests/test_backend.py::TestTouchless::test_verify_invoice_holds_release_blocked PASSED [ 47%]
../tests/test_backend.py::TestRecon::test_tied_with_explained_items PASSED [ 50%]
../tests/test_backend.py::TestRecon::test_not_tied_when_unexplained PASSED [ 52%]
../tests/test_backend.py::TestRecon::test_unexplained_derived_when_missing PASSED [ 54%]
../tests/test_backend.py::TestRecon::test_no_rows_is_not_tied PASSED     [ 56%]
../tests/test_backend.py::TestRecon::test_recon_endpoint PASSED          [ 58%]
../tests/test_backend.py::TestChatRouting::test_genie_when_mas_empty PASSED [ 60%]
../tests/test_backend.py::TestChatRouting::test_mas_wins_when_set PASSED [ 62%]
../tests/test_backend.py::TestChatRouting::test_sql_agent_last_resort PASSED [ 64%]
../tests/test_backend.py::TestChatRouting::test_stream_uses_genie_route PASSED [ 66%]
../tests/test_backend.py::TestChatRouting::test_genie_failure_falls_back_to_sql_agent PASSED [ 68%]
../tests/test_backend.py::TestChatRouting::test_ask_genie_api_flow_with_obo_then_sp_fallback PASSED [ 70%]
../tests/test_backend.py::TestNoSilentMocks::test_typed_503_banner_and_recovery PASSED [ 72%]
../tests/test_backend.py::TestNoSilentMocks::test_statement_error_is_not_an_outage PASSED [ 75%]
../tests/test_backend.py::TestNoSilentMocks::test_demo_mode_only_when_explicit PASSED [ 77%]
../tests/test_backend.py::TestNoSilentMocks::test_unknown_invoice_is_404_not_fixture PASSED [ 79%]
../tests/test_backend.py::TestNoSilentMocks::test_auto_matched_from_data_and_date_order PASSED [ 81%]
../tests/test_backend.py::TestNoSilentMocks::test_streams_use_random_only_for_timing PASSED [ 83%]
../tests/test_backend.py::TestNoSilentMocks::test_stream_emits_typed_error PASSED [ 85%]
../tests/test_backend.py::TestNoSilentMocks::test_p2p_stream_flags_release_blocked PASSED [ 87%]
../tests/test_backend.py::TestObo::test_user_token_used_for_reads PASSED [ 89%]
../tests/test_backend.py::TestObo::test_sp_without_header PASSED         [ 91%]
../tests/test_backend.py::TestExceptionQueue::test_served_from_lakebase PASSED [ 93%]
../tests/test_backend.py::TestExceptionQueue::test_warehouse_fallback_is_flagged PASSED [ 95%]
../tests/test_backend.py::TestExceptionQueue::test_queue_table_identifier_quoted PASSED [ 97%]
../tests/test_backend.py::TestExceptionQueue::test_debug_status_shape PASSED [100%]
======================== 48 passed, 1 warning in 1.37s =========================
```

## Frontend tests (Playwright, mocked APIs, local Vite) — 80 passed, 0 failed

`./tests/run_tests.sh frontend`

```
  10 skipped
  80 passed (1.4m)
```

The 10 skipped tests are `tests/test_e2e_deployed.spec.ts`, which runs only when `APP_URL` is set and needs an
authenticated browser session for the Databricks Apps login. The deployed app is verified at API level instead, with
a workspace token: `app_api_responses.md` (every endpoint 200, including approval, call log and chat).

Nine frontend tests that failed on the baseline UI (loose text locators matching hidden tabs) were fixed by scoping
their locators; see `docs/testing.md`. One finding: at a 375 px viewport the fixed 380 px chat panel hides the main
content until the panel is closed.
