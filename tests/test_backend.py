"""
Finance & Accounting Control Tower — Backend Test Suite
========================================================
Runs locally with mocks: no workspace, warehouse, Genie space or Lakebase needed.

Run:
    ./tests/run_tests.sh backend
    # or: cd app && PYTHONPATH=. pytest ../tests/test_backend.py -v

Covers the FE BAR fixes:
  F1  recon "Tied" only when the unexplained delta is zero; items surfaced
  F2  touchless excludes release-blocked invoices; verify-invoice HOLDs them
  F5  chat routes to Genie when no MAS endpoint is set; Genie API flow; fallback
  F6  no silent mock data: typed 503 + banner, recovery, DEMO_MODE only when set,
      data-derived auto_matched, posting-date replay order
  F8  on-behalf-of-user token used for warehouse reads
  F9  sqlglot SQL guard: DDL, DML, multi-statement, off-list tables, LIMIT
"""
import asyncio
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("DATABRICKS_HOST", "https://example.cloud.databricks.com")
os.environ.setdefault("DATABRICKS_CATALOG", "cat")
os.environ.setdefault("DATABRICKS_SCHEMA", "sch")
os.environ.setdefault("DATABRICKS_TOKEN", "sp-token")
os.environ.setdefault("QUERY_RETRY_BACKOFF", "0")

from fastapi.testclient import TestClient  # noqa: E402

with patch("backend.db.query", return_value=[{"ok": 1}]), \
     patch("backend.lakebase.init_schema", return_value=None):
    from backend import main, db, chat, streams, lakebase, config  # noqa: E402
    from backend.sql_guard import guard_sql, SqlGuardError  # noqa: E402

CAT, SCH = config.CATALOG, config.SCHEMA


@pytest.fixture()
def client():
    # Patches cover app startup only (warehouse probe + Lakebase DDL), not the test body.
    p1 = patch("backend.lakebase.init_schema", return_value=None)
    p2 = patch("backend.db.query", return_value=[{"ok": 1}])
    p1.start(); p2.start()
    c = TestClient(main.app, raise_server_exceptions=False)
    c.__enter__()
    p1.stop(); p2.stop()
    try:
        yield c
    finally:
        c.__exit__(None, None, None)


@pytest.fixture(autouse=True)
def _reset_status():
    db._status.update(live=None, last_error=None, last_success_at=None, last_failure_at=None)
    yield


def run(coro_gen):
    """Collect an async generator into a list."""
    async def _collect():
        return [x async for x in coro_gen]
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════════

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "healthy"


def test_me_reads_forwarded_identity(client):
    r = client.get("/api/me", headers={"x-forwarded-email": "jane.doe@example.com"})
    assert r.json()["name"] == "Jane"


# ═══════════════════════════════════════════════════════════════
# F9 — SQL guard
# ═══════════════════════════════════════════════════════════════

class TestSqlGuard:
    @pytest.mark.parametrize("sql", [
        "DROP TABLE gold_fact_invoices",
        "CREATE TABLE gold_x AS SELECT 1",
        "ALTER TABLE gold_fact_gl ADD COLUMN x INT",
        "GRANT SELECT ON gold_fact_gl TO `someone`",
    ])
    def test_rejects_ddl(self, sql):
        with pytest.raises(SqlGuardError):
            guard_sql(sql, CAT, SCH)

    @pytest.mark.parametrize("sql", [
        "DELETE FROM gold_fact_invoices",
        "UPDATE gold_fact_invoices SET release_blocked = false",
        "INSERT INTO gold_fact_gl SELECT * FROM gold_fact_gl",
        "MERGE INTO gold_fact_gl t USING gold_fact_gl s ON t.je_id = s.je_id WHEN MATCHED THEN DELETE",
    ])
    def test_rejects_dml(self, sql):
        with pytest.raises(SqlGuardError):
            guard_sql(sql, CAT, SCH)

    def test_rejects_multiple_statements(self):
        with pytest.raises(SqlGuardError, match="exactly one statement"):
            guard_sql("SELECT * FROM gold_fact_gl; DROP TABLE gold_fact_gl", CAT, SCH)

    @pytest.mark.parametrize("sql", [
        "SELECT * FROM bronze_vendors",
        "SELECT * FROM silver_invoice_extractions",          # masked PII source, not on list
        "SELECT * FROM system.access.audit",
        "SELECT * FROM gold_fact_invoices WHERE vendor_id IN (SELECT vendor_id FROM bronze_vendors)",
    ])
    def test_rejects_off_list_tables(self, sql):
        with pytest.raises(SqlGuardError, match="allow-list"):
            guard_sql(sql, CAT, SCH)

    def test_rejects_other_schema(self):
        with pytest.raises(SqlGuardError, match="schema"):
            guard_sql("SELECT * FROM other_schema.gold_fact_gl", CAT, SCH)

    def test_adds_limit_and_qualifies(self):
        out = guard_sql("SELECT invoice_id FROM gold_fact_invoices", CAT, SCH)
        assert out.endswith("LIMIT 100")
        assert f"{CAT}.{SCH}.gold_fact_invoices" in out

    def test_clamps_large_limit(self):
        assert guard_sql("SELECT * FROM gold_fact_gl LIMIT 5000", CAT, SCH).endswith("LIMIT 100")

    def test_keeps_small_limit_and_ctes(self):
        out = guard_sql("WITH x AS (SELECT * FROM gold_recon_subledger_vs_gl) SELECT * FROM x LIMIT 5", CAT, SCH)
        assert out.endswith("LIMIT 5")

    def test_allows_exceptions_and_eval_tables(self):
        guard_sql("SELECT exception_type, COUNT(*) FROM silver_invoice_exceptions GROUP BY 1", CAT, SCH)
        guard_sql("SELECT * FROM gold_ai_extraction_eval", CAT, SCH)

    def test_sql_agent_refuses_generated_ddl(self):
        async def fake_fmapi(*a, **k):
            return "DROP TABLE gold_fact_invoices"
        with patch.object(chat, "_fmapi_chat", fake_fmapi), \
             patch.object(chat.db, "query") as q:
            events = run(chat.stream_sql_agent("drop everything"))
        assert events[-1]["type"] == "error" and "rejected by policy" in events[-1]["message"]
        q.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# F2 — touchless excludes release-blocked; verify-invoice HOLDs
# ═══════════════════════════════════════════════════════════════

class TestTouchless:
    def test_touchless_query_excludes_release_blocked(self):
        seen = []

        def fake_query(sql, params=None):
            seen.append(sql)
            if "silver_invoice_exceptions" in sql:
                return [{"exception_type": "EXTRACTION_MISMATCH", "n": 3},
                        {"exception_type": "NO_PO_REFERENCE", "n": 7}]
            return [{"total_invoices": 100, "matched": 40, "touchless": 37, "release_blocked": 3,
                     "release_blocked_amount": 900.0, "amount_mismatch": 5, "no_po": 7, "two_way": 2,
                     "overdue_count": 1, "total_amount": 10.0, "overdue_amount": 1.0,
                     "avg_aging_days": 20, "touchless_rate": 37.0}]

        with patch.object(db, "query", side_effect=fake_query):
            m = db.get_p2p_metrics()
        kpi_sql = seen[0]
        assert "NOT COALESCE(release_blocked, false)" in kpi_sql
        assert kpi_sql.count(db.TOUCHLESS_PREDICATE) >= 2  # count + rate
        assert m["touchless"] == 37 and m["matched"] == 40 and m["release_blocked"] == 3
        assert m["extraction_mismatch"] == 3 and m["exceptions"] == 10

    def test_verify_invoice_holds_release_blocked(self, client):
        inv = {"invoice_id": "INV000033", "invoice_number": "VINV-2026-1", "vendor_id": "VND0001",
               "vendor_name": "Acme", "po_id": "PO00001", "invoice_amount": 100.0,
               "invoice_total_inr": 118.0, "gstin_vendor": "27ABCDE1234F1Z5", "match_status": "THREE_WAY_MATCHED",
               "release_blocked": True, "block_reason": "PDF total differs from ERP by -10.0%",
               "po_total_amount": 100.0, "vendor_master_gstin": "27ABCDE1234F1Z5", "vendor_is_active": True,
               "extracted_vendor_name": "Acme", "extracted_total_amount": 106.2,
               "extracted_gstin": "27ABCDE1234F1Z5", "extracted_po_reference": "PO00001"}

        def fake_query(sql, params=None):
            if "gold_recon_subledger_vs_gl" in sql:
                return [{"account_code": "2000", "account_name": "AP", "subledger_amount": 10.0,
                         "gl_amount": 8.0, "delta": 2.0, "reconciling_items_amount": 2.0,
                         "reconciling_items_count": 1, "unexplained_delta": 0.0}]
            if "gold_recon_reconciling_items" in sql:
                return []
            if "COUNT(*) AS dups" in sql:
                return [{"dups": 0}]
            return [inv]

        with patch.object(db, "query", side_effect=fake_query):
            r = client.get("/api/verify-invoice/INV000033")
        body = r.json()
        assert r.status_code == 200
        assert body["release_blocked"] is True
        assert body["recommendation"]["label"] == "HOLD"
        ai = next(c for c in body["checks"] if c["id"] == 2)
        assert ai["status"] == "FAIL" and "RELEASE BLOCKED" in ai["detail"]
        assert body["pdf_total"] == 106.2 and body["erp_total"] == 118.0


# ═══════════════════════════════════════════════════════════════
# F1 — reconciliation
# ═══════════════════════════════════════════════════════════════

class TestRecon:
    ROW = {"account_code": "1100", "account_name": "Accounts Receivable", "subledger_source": "gold_fact_collections",
           "subledger_amount": 1000.0, "gl_amount": 700.0, "delta": 300.0,
           "reconciling_items_amount": 300.0, "reconciling_items_count": 2,
           "unexplained_delta": 0.0, "tied": True, "cutoff_date": "2026-09-30"}
    ITEMS = [{"account_code": "1100", "document_id": "CINV000010", "document_type": "AR_INVOICE",
              "amount": 200.0, "reason": "Posted to sub-ledger after GL cut-off", "gl_je_id": None, "gl_je_status": None},
             {"account_code": "1100", "document_id": "CINV000011", "document_type": "AR_INVOICE",
              "amount": 100.0, "reason": "Posted to sub-ledger after GL cut-off", "gl_je_id": None, "gl_je_status": None}]

    def test_tied_with_explained_items(self):
        out = db.shape_recon([self.ROW], self.ITEMS)
        r = out["rows"][0]
        assert r["delta"] == 300.0 and r["reconciling_items_amount"] == 300.0
        assert r["tied"] is True and out["all_tied"] is True
        assert len(r["items"]) == 2

    def test_not_tied_when_unexplained(self):
        bad = {**self.ROW, "reconciling_items_amount": 250.0, "unexplained_delta": 50.0, "tied": True}
        out = db.shape_recon([bad], self.ITEMS)
        # The stored flag is ignored: arithmetic decides.
        assert out["rows"][0]["tied"] is False and out["all_tied"] is False

    def test_unexplained_derived_when_missing(self):
        row = {k: v for k, v in self.ROW.items() if k != "unexplained_delta"}
        row["reconciling_items_amount"] = 100.0
        assert db.shape_recon([row], [])["rows"][0]["unexplained_delta"] == 200.0

    def test_no_rows_is_not_tied(self):
        assert db.shape_recon([], [])["all_tied"] is False

    def test_recon_endpoint(self, client):
        def fake_query(sql, params=None):
            return [self.ROW] if "subledger_vs_gl" in sql else self.ITEMS
        with patch.object(db, "query", side_effect=fake_query):
            r = client.get("/api/recon")
        j = r.json()
        assert r.status_code == 200 and j["all_tied"] is True
        assert j["rows"][0]["reconciling_items_count"] == 2


# ═══════════════════════════════════════════════════════════════
# F5 — chat routing / Genie
# ═══════════════════════════════════════════════════════════════

class TestChatRouting:
    def test_genie_when_mas_empty(self):
        with patch.object(chat, "MAS_ENDPOINT", ""), patch.object(chat, "GENIE_SPACE_ID", "space-1"):
            assert chat.select_route() == "genie"

    def test_mas_wins_when_set(self):
        with patch.object(chat, "MAS_ENDPOINT", "mas-x"), patch.object(chat, "GENIE_SPACE_ID", "space-1"):
            assert chat.select_route() == "mas"

    def test_sql_agent_last_resort(self):
        with patch.object(chat, "MAS_ENDPOINT", ""), patch.object(chat, "GENIE_SPACE_ID", ""):
            assert chat.select_route() == "sql_agent"

    def test_stream_uses_genie_route(self):
        async def fake_ask(q, user_token=None, conversation_id=None):
            return {"text": "3 invoices are blocked.", "sql": "SELECT 1", "columns": ["invoice_id"],
                    "rows": [["INV000033"]], "conversation_id": "c1", "message_id": "m1",
                    "status": "COMPLETED", "auth": "obo"}
        with patch.object(chat, "MAS_ENDPOINT", ""), patch.object(chat, "GENIE_SPACE_ID", "space-1"), \
             patch.object(chat, "ask_genie", fake_ask):
            evs = run(chat.stream_mas_agent([{"role": "user", "content": "blocked?"}], user_token="u"))
        text = "".join(e["text"] for e in evs if e["type"] == "chunk")
        done = evs[-1]
        assert "INV000033" in text and "| invoice_id |" in text
        assert done["route"] == "genie" and done["response_id"] == "genie:c1" and done["sql"] == "SELECT 1"

    def test_genie_failure_falls_back_to_sql_agent(self):
        async def boom(*a, **k):
            raise RuntimeError("space not found")

        async def fake_sql_agent(question, active_tab="P2P", user_token=None, history=None):
            yield {"type": "chunk", "text": "fallback answer"}
            yield {"type": "done", "route": "sql_agent", "response_id": None, "tool": "finance-sql-agent"}

        with patch.object(chat, "MAS_ENDPOINT", ""), patch.object(chat, "GENIE_SPACE_ID", "space-1"), \
             patch.object(chat, "ask_genie", boom), patch.object(chat, "stream_sql_agent", fake_sql_agent):
            evs = run(chat.stream_mas_agent([{"role": "user", "content": "q"}]))
        assert evs[-1]["route"] == "sql_agent"
        assert any("Genie unavailable" in e.get("text", "") for e in evs)

    def test_ask_genie_api_flow_with_obo_then_sp_fallback(self):
        calls = []

        async def fake_http(session, method, url, token, payload=None):
            calls.append((method, url.split("/spaces/space-1")[1], token))
            if url.endswith("/start-conversation"):
                if token == "user-tok":
                    return 403, {"error": "missing scope"}
                return 200, {"conversation_id": "c9", "message_id": "m9"}
            if url.endswith("/query-result"):
                return 200, {"statement_response": {
                    "manifest": {"schema": {"columns": [{"name": "n"}]}},
                    "result": {"data_array": [["3"]]}}}
            return 200, {"status": "COMPLETED", "attachments": [
                {"attachment_id": "a1", "query": {"query": "SELECT COUNT(*) n FROM x", "description": "Count"}}]}

        with patch.object(chat, "GENIE_SPACE_ID", "space-1"), patch.object(chat, "_http", fake_http), \
             patch.object(chat, "get_token", return_value="sp-tok"):
            res = asyncio.run(chat.ask_genie("how many?", user_token="user-tok"))
        assert res["auth"] == "sp" and res["rows"] == [["3"]] and res["sql"].startswith("SELECT")
        assert calls[0][2] == "user-tok" and calls[1][2] == "sp-tok"
        assert any(c[1].endswith("/attachments/a1/query-result") for c in calls)


# ═══════════════════════════════════════════════════════════════
# F6 — no silent mock data
# ═══════════════════════════════════════════════════════════════

class TestNoSilentMocks:
    def test_typed_503_banner_and_recovery(self, client):
        with patch.object(db, "RETRIES", 2), patch.object(db, "BACKOFF_S", 0), \
             patch.object(db, "get_connection", side_effect=ConnectionError("warehouse STARTING")):
            r = client.get("/api/metrics/p2p")
            s = client.get("/api/data-status").json()
        assert r.status_code == 503 and r.json()["error"] == "warehouse_unavailable"
        assert s["live"] is False and s["banner"].startswith("Warehouse starting")

        cur = MagicMock()
        cur.description = [("ok",)]
        cur.fetchall.return_value = [(1,)]
        conn = MagicMock()
        conn.cursor.return_value = cur
        with patch.object(db, "get_connection", return_value=conn):
            s2 = client.get("/api/data-status").json()
        assert s2["live"] is True and s2["banner"] is None  # recovered without restart

    def test_statement_error_is_not_an_outage(self):
        with patch.object(db, "get_connection",
                          side_effect=Exception("[TABLE_OR_VIEW_NOT_FOUND] gold_x not found")):
            with pytest.raises(db.QueryError):
                db.query("SELECT * FROM gold_x")
        assert db._status["live"] is True

    def test_demo_mode_only_when_explicit(self, client):
        assert config.DEMO_MODE is False
        with patch.object(db, "DEMO_MODE", True), patch.object(main, "DEMO_MODE", True):
            m = client.get("/api/metrics/p2p").json()["metrics"]
            s = client.get("/api/data-status").json()
        assert m["demo"] is True
        assert s["banner"].startswith("Demo data")

    def test_unknown_invoice_is_404_not_fixture(self, client):
        with patch.object(db, "query", return_value=[]):
            r = client.get("/api/invoice/INV999999")
        assert r.status_code == 404

    def test_auto_matched_from_data_and_date_order(self):
        rows = [  # newest first, as the query returns them
            {"o2c_invoice_id": "C3", "invoice_date": "2026-09-03", "amount_collected_inr": 0, "balance_outstanding": 5,
             "auto_matched": False, "days_overdue": 0, "invoice_status": "OUTSTANDING"},
            {"o2c_invoice_id": "C2", "invoice_date": "2026-09-02", "amount_collected_inr": 40, "balance_outstanding": 60,
             "auto_matched": False, "days_overdue": 0, "invoice_status": "PARTIAL_PAID"},
            {"o2c_invoice_id": "C1", "invoice_date": "2026-09-01", "amount_collected_inr": 100, "balance_outstanding": 0,
             "auto_matched": True, "days_overdue": 0, "invoice_status": "PAID"},
        ]

        async def nosleep(*_):
            return None

        with patch.object(db, "get_collections", return_value=rows), patch.object(streams.asyncio, "sleep", nosleep):
            evs = [json.loads(e) for e in run(streams.stream_o2c())]
        feed = [e for e in evs if e["type"] in ("payment_received", "collection")]
        assert [e["data"]["o2c_invoice_id"] for e in feed] == ["C1", "C2", "C3"]
        pays = {e["data"]["o2c_invoice_id"]: e["data"]["auto_matched"] for e in feed if e["type"] == "payment_received"}
        assert pays == {"C1": True, "C2": False}

    def test_streams_use_random_only_for_timing(self):
        src = open(os.path.join(APP_DIR, "backend", "streams.py")).read()
        import re
        uses = re.findall(r"random\.(\w+)", src)
        assert set(uses) <= {"uniform"}, uses
        assert "shuffle" not in src

    def test_stream_emits_typed_error(self):
        with patch.object(db, "get_invoices", side_effect=db.WarehouseUnavailable("down")):
            evs = [json.loads(e) for e in run(streams.stream_p2p())]
        assert evs == [{"type": "error", "data": {"error": "warehouse_unavailable", "message": "down"}}]

    def test_p2p_stream_flags_release_blocked(self):
        inv = {"invoice_id": "INV000033", "match_status": "THREE_WAY_MATCHED", "release_blocked": True,
               "block_reason": "PDF total differs", "invoice_total_inr": 118.0, "ai_extracted_amount": 106.2,
               "gstin_vendor": "27X", "is_overdue": False}
        excs = streams._detect_p2p_exceptions(inv)
        assert excs[0]["rule"] == "release_blocked" and "PDF ≠ ERP" in excs[0]["reason"]


# ═══════════════════════════════════════════════════════════════
# F8 — on-behalf-of-user reads
# ═══════════════════════════════════════════════════════════════

class TestObo:
    def _conn(self):
        cur = MagicMock()
        cur.description = [("ok",)]
        cur.fetchall.return_value = [(1,)]
        conn = MagicMock()
        conn.cursor.return_value = cur
        return conn

    def test_user_token_used_for_reads(self, client):
        with patch.object(db.dbsql, "connect", return_value=self._conn()) as connect:
            client.get("/api/data-status", headers={"x-forwarded-access-token": "user-abc"})
            st = client.get("/api/debug/status", headers={"x-forwarded-access-token": "user-abc"}).json()
        assert connect.call_args.kwargs["access_token"] == "user-abc"
        assert connect.call_args.kwargs["catalog"] == CAT
        assert st["auth_mode"] == "obo"

    def test_sp_without_header(self, client):
        with patch.object(db.dbsql, "connect", return_value=self._conn()) as connect:
            client.get("/api/data-status")
        assert connect.call_args.kwargs["access_token"] == "sp-token"
        assert config.current_user_token() is None  # context cleared after the request


# ═══════════════════════════════════════════════════════════════
# F5 — Lakebase operational serving
# ═══════════════════════════════════════════════════════════════

class TestExceptionQueue:
    def test_served_from_lakebase(self, client):
        with patch.object(lakebase, "get_ap_exception_queue", return_value=[{"invoice_id": "INV000033"}]):
            j = client.get("/api/ap/exception-queue").json()
        assert j["source"] == "lakebase" and j["rows"][0]["invoice_id"] == "INV000033"

    def test_warehouse_fallback_is_flagged(self, client):
        with patch.object(lakebase, "get_ap_exception_queue", return_value=None), \
             patch.object(db, "query", return_value=[{"invoice_id": "INV000033"}]):
            j = client.get("/api/ap/exception-queue/INV000033").json()
        assert j["source"] == "warehouse" and j["row"]["invoice_id"] == "INV000033"

    def test_queue_table_identifier_quoted(self):
        with patch.object(lakebase, "LAKEBASE_QUEUE_TABLE", "finance_ops_control_tower.ap_exception_queue"):
            assert lakebase._queue_table_sql() == '"finance_ops_control_tower"."ap_exception_queue"'
        with patch.object(lakebase, "LAKEBASE_QUEUE_TABLE", "x; DROP TABLE y"):
            with pytest.raises(ValueError):
                lakebase._queue_table_sql()

    def test_debug_status_shape(self, client):
        with patch.object(db, "query", return_value=[{"ok": 1}]):
            st = client.get("/api/debug/status").json()
        for k in ("demo_mode", "auth_mode", "db", "lakebase", "genie"):
            assert k in st
        assert "connected" in st["lakebase"] and "configured" in st["genie"]
        assert st["genie"]["chat_route"] in ("mas", "genie", "sql_agent")
