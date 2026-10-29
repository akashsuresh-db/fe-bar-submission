# Testing

Two suites cover the app. Both run without a workspace when mocked; the deployed suite needs the app URL.

| Suite | File | Runs against | Command |
|---|---|---|---|
| Backend (pytest, mocked) | `tests/test_backend.py` | FastAPI app in-process; warehouse, Genie and Lakebase mocked | `./tests/run_tests.sh backend` |
| Frontend (Playwright, mocked APIs) | `tests/test_frontend.spec.ts` | Local Vite dev server (`LOCAL_URL`, default `http://localhost:5173`) | `./tests/run_tests.sh frontend` |
| Deployed app (Playwright) | `tests/test_e2e_deployed.spec.ts` | The deployed Databricks App; skipped unless `APP_URL` is set | `APP_URL=https://<app>.databricksapps.com ./tests/run_tests.sh frontend` |

## What the backend suite proves

| Fix | Tests |
|---|---|
| F1 reconciliation | `TestRecon`: "Tied" only when the unexplained delta is zero; a stored `tied` flag is overridden by the arithmetic; reconciling items are returned per account |
| F2 AI release control | `TestTouchless`: the touchless KPI SQL excludes `release_blocked`; `/api/verify-invoice` returns `HOLD` with the block reason and PDF vs ERP totals |
| F5 Genie wiring | `TestChatRouting`: Genie is chosen when `MAS_ENDPOINT_NAME` is empty; the Conversation API flow (start → poll → query-result); user token first, service principal on 401/403; fallback to the guarded SQL agent |
| F5 Lakebase serving | `TestExceptionQueue`: the AP queue is served from the Lakebase synced table, a warehouse fallback is labelled, the Postgres identifier is quoted |
| F6 no silent mocks | `TestNoSilentMocks`: typed 503 + banner when the warehouse is down and recovery without restart; statement errors are not treated as outages; demo data only with `DEMO_MODE=true`; unknown invoices are 404; `auto_matched` comes from data; replay is in posting-date order; `random` is used only for pacing |
| F8 on-behalf-of-user | `TestObo`: the forwarded `x-forwarded-access-token` is the warehouse credential; the service principal is used when no header is present |
| F9 SQL guard | `TestSqlGuard`: DDL, DML, multiple statements, off-list tables and other schemas are rejected; `LIMIT` is added or clamped to 100; the SQL agent never executes rejected SQL |

## Known pre-existing frontend test failures

Nine tests in `tests/test_frontend.spec.ts` fail on the baseline UI (fins-demo `d033c92`) as well as on the current build. They use loose text locators that resolve to hidden elements of other mounted tabs (for example `/JE/i` matches "Rajesh"):
`can switch to R2R tab`, `call log modal shows four outcome options`, `modal close (X) button dismisses modal`, `Trial Balance table shows account codes`, `Trial Balance table shows DR/CR labels`, `New Chat button clears conversation`, `History button shows session list panel`, `drawer shows resolution text`, `tab navigation still works on small viewport`.

## Troubleshooting streams (SSE)

- The Databricks Apps proxy must not buffer SSE: responses set `X-Accel-Buffering: no` and `Cache-Control: no-cache`.
- A stream that cannot reach the warehouse emits one typed event, `{"type":"error","data":{"error":"warehouse_unavailable"}}`, which the UI shows as a stream error; it never emits fixture rows.
- `GET /api/data-status` reports whether the backend is serving live rows; `GET /api/debug/status` adds Lakebase, Genie, auth mode and escalation state.
- App logs: `databricks apps logs <app-name> -p <profile>` (OAuth profiles only).
