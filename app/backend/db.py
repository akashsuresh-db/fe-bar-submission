"""Database module using databricks-sql-connector.

Reads run on behalf of the signed-in user (x-forwarded-access-token) so Unity
Catalog row filters and column masks apply; the app service principal is used
only when there is no request context (startup probe).

Failure handling (no silent mock data):
  - DEMO_MODE=true   → fixture metrics, flagged as demo in /api/data-status.
  - otherwise        → retry with backoff (the warehouse may be starting), then
                       raise WarehouseUnavailable → HTTP 503 + UI banner. The next
                       successful query flips the status back to live.
"""
import os
import time
import datetime
from typing import Any
from databricks import sql as dbsql
from backend.config import (
    get_workspace_host, get_read_token, auth_mode, WAREHOUSE_ID, CATALOG, SCHEMA,
    DEMO_MODE, full_table,
)


class WarehouseUnavailable(Exception):
    """The SQL warehouse could not be reached after retries (or demo mode is on)."""


class QueryError(Exception):
    """The warehouse answered but rejected the statement (bad SQL, missing table, no permission)."""


# Live-data status, surfaced via /api/data-status and /api/debug/status.
_status: dict[str, Any] = {
    "live": None,              # None = not probed yet, True = last query succeeded
    "last_error": None,
    "last_success_at": None,
    "last_failure_at": None,
    "last_auth_mode": None,
}

# Errors that retrying will not fix.
_NON_RETRYABLE = (
    "TABLE_OR_VIEW_NOT_FOUND", "UNRESOLVED_COLUMN", "PARSE_SYNTAX_ERROR",
    "PERMISSION_DENIED", "INSUFFICIENT_PERMISSIONS", "UNRESOLVED_ROUTINE",
    "DATATYPE_MISMATCH", "SQLSTATE: 42",
)

RETRIES = int(os.environ.get("QUERY_RETRIES", "3"))
BACKOFF_S = float(os.environ.get("QUERY_RETRY_BACKOFF", "2"))


def data_status() -> dict:
    """Whether the backend is currently serving live rows."""
    return {
        "demo_mode": DEMO_MODE,
        "live": False if DEMO_MODE else _status["live"],
        "last_error": _status["last_error"],
        "last_success_at": _status["last_success_at"],
        "last_failure_at": _status["last_failure_at"],
        "auth_mode": _status["last_auth_mode"],
        "warehouse_id": WAREHOUSE_ID,
    }


def get_connection():
    """Create a new Databricks SQL connection (user token when available)."""
    host = get_workspace_host().replace("https://", "")
    return dbsql.connect(
        server_hostname=host,
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE_ID}",
        access_token=get_read_token(),
        catalog=CATALOG,
        schema=SCHEMA,
    )


def _is_non_retryable(e: Exception) -> bool:
    msg = str(e)
    return any(tok in msg for tok in _NON_RETRYABLE)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def query(sql: str, params: dict | None = None) -> list[dict[str, Any]]:
    """Execute a SQL query and return rows as dicts.

    Raises QueryError for statement errors and WarehouseUnavailable when the
    warehouse cannot be reached after retries. Never returns invented data.
    """
    if DEMO_MODE:
        raise WarehouseUnavailable("DEMO_MODE=true — warehouse queries disabled")

    last_exc: Exception | None = None
    for attempt in range(max(RETRIES, 1)):
        try:
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(sql, parameters=params)
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
            finally:
                conn.close()
            _status.update(live=True, last_error=None, last_success_at=_now(),
                           last_auth_mode=auth_mode())
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            last_exc = e
            if _is_non_retryable(e):
                # The warehouse is up — this is a statement problem, not an outage.
                _status.update(live=True, last_auth_mode=auth_mode())
                raise QueryError(str(e)[:500]) from e
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF_S * (2 ** attempt))

    _status.update(live=False, last_error=str(last_exc)[:300], last_failure_at=_now())
    print(f"Warehouse unavailable after {RETRIES} attempt(s): {last_exc}")
    raise WarehouseUnavailable(str(last_exc)[:300])


# ─── Demo fixtures (served ONLY when DEMO_MODE=true) ──────────

def _get_p2p_demo_metrics() -> dict:
    return {
        "total_invoices": 142, "matched": 111, "touchless": 108, "release_blocked": 3,
        "release_blocked_amount": 1_250_000, "two_way": 15, "amount_mismatch": 5,
        "no_po": 4, "extraction_mismatch": 3, "exceptions": 34, "exceptions_by_type": {},
        "overdue_count": 8, "total_amount": 47_500_000, "overdue_amount": 2_100_000,
        "avg_aging_days": 21.5, "touchless_rate": 76.1, "demo": True,
    }


def _get_payment_run_demo_data() -> dict:
    return {"total_payments": 89, "total_paid": 32_750_000, "avg_dpo": 42.3,
            "early_payments": 12, "on_time_payments": 65, "late_payments": 12, "demo": True}


def _get_o2c_demo_metrics() -> dict:
    return {
        "total_outstanding": 28_500_000, "avg_dso": 52.4, "total_invoices": 156,
        "collected": 132, "total_collected": 76_400_000, "overdue_count": 24, "cei": 89.5,
        "aging_buckets": [
            {"bucket": "0-30 days", "count": 98, "amount": 14_700_000},
            {"bucket": "31-60 days", "count": 35, "amount": 8_900_000},
            {"bucket": "61-90 days", "count": 18, "amount": 3_200_000},
            {"bucket": "90+ days", "count": 5, "amount": 1_700_000},
        ],
        "customers_at_risk": [], "demo": True,
    }


def _get_r2r_demo_metrics() -> dict:
    return {"total_jes": 247, "total_lines": 1248, "total_debits": 125_400_000,
            "total_credits": 125_400_000, "posted": 201, "pending": 46,
            "tb_total_debit": 385_250_000, "tb_total_credit": 385_250_000,
            "tb_imbalance": 0.0, "is_balanced": True, "trial_balance": [], "demo": True}


# ─── P2P Queries ─────────────────────────────────────────────

# Touchless = clean 3-way match that the AI release control did NOT block.
# A tampered PDF can still 3-way match on ERP data; it must not count as touchless.
TOUCHLESS_PREDICATE = "match_status = 'THREE_WAY_MATCHED' AND NOT COALESCE(release_blocked, false)"


def get_invoices(limit: int = 200) -> list[dict]:
    """Most recent invoices from Gold (newest first; the stream replays them oldest first)."""
    return query(f"""
        SELECT i.invoice_id, i.invoice_number, i.vendor_name, i.vendor_category,
               i.invoice_date, i.due_date, i.invoice_amount, i.tax_amount,
               i.invoice_total_inr, i.match_status, i.has_po_ref, i.is_overdue,
               i.aging_days, i.aging_bucket, i.invoice_status, i.po_id, i.gstin_vendor,
               i.pdf_file_path, i.data_source, i.legal_entity,
               i.release_blocked, i.block_reason, i.ai_extracted_amount,
               e.exception_type,
               x.extracted_vendor_name, x.extracted_total_amount, x.extracted_gstin,
               x.extracted_po_reference,
               p.total_amount AS po_total_amount
        FROM {full_table('gold_fact_invoices')} i
        LEFT JOIN {full_table('silver_invoice_exceptions')} e ON i.invoice_id = e.invoice_id
        LEFT JOIN {full_table('silver_invoice_extractions')} x ON i.invoice_id = x.invoice_id
        LEFT JOIN {full_table('silver_po_header')} p           ON i.po_id      = p.po_id
        ORDER BY i.invoice_date DESC, i.invoice_id
        LIMIT {int(limit)}
    """)


def get_p2p_metrics() -> dict:
    """Get AP/P2P KPI metrics."""
    if DEMO_MODE:
        return _get_p2p_demo_metrics()

    rows = query(f"""
        SELECT
            COUNT(*) as total_invoices,
            SUM(CASE WHEN match_status = 'THREE_WAY_MATCHED' THEN 1 ELSE 0 END) as matched,
            SUM(CASE WHEN {TOUCHLESS_PREDICATE} THEN 1 ELSE 0 END) as touchless,
            SUM(CASE WHEN COALESCE(release_blocked, false) THEN 1 ELSE 0 END) as release_blocked,
            SUM(CASE WHEN COALESCE(release_blocked, false) THEN invoice_total_inr ELSE 0 END) as release_blocked_amount,
            SUM(CASE WHEN match_status = 'AMOUNT_MISMATCH' THEN 1 ELSE 0 END) as amount_mismatch,
            SUM(CASE WHEN match_status = 'NO_PO_REFERENCE' THEN 1 ELSE 0 END) as no_po,
            SUM(CASE WHEN match_status = 'TWO_WAY_MATCHED' THEN 1 ELSE 0 END) as two_way,
            SUM(CASE WHEN is_overdue = true THEN 1 ELSE 0 END) as overdue_count,
            SUM(invoice_total_inr) as total_amount,
            SUM(CASE WHEN is_overdue = true THEN invoice_total_inr ELSE 0 END) as overdue_amount,
            AVG(CASE WHEN aging_days > 0 THEN aging_days END) as avg_aging_days,
            ROUND(SUM(CASE WHEN {TOUCHLESS_PREDICATE} THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as touchless_rate
        FROM {full_table('gold_fact_invoices')}
    """)
    by_type = query(f"""
        SELECT exception_type, COUNT(*) AS n
        FROM {full_table('silver_invoice_exceptions')}
        GROUP BY exception_type
    """)
    if not rows:
        return {}
    r = rows[0]
    exc = {t["exception_type"]: int(t["n"] or 0) for t in by_type}
    return {
        "total_invoices": r.get("total_invoices", 0),
        "matched": r.get("matched", 0),
        "touchless": r.get("touchless", 0),
        "release_blocked": r.get("release_blocked", 0),
        "release_blocked_amount": float(r.get("release_blocked_amount", 0) or 0),
        "two_way": r.get("two_way", 0),
        "amount_mismatch": r.get("amount_mismatch", 0),
        "no_po": r.get("no_po", 0),
        "extraction_mismatch": exc.get("EXTRACTION_MISMATCH", 0),
        "exceptions": sum(exc.values()),
        "exceptions_by_type": exc,
        "overdue_count": r.get("overdue_count", 0),
        "total_amount": float(r.get("total_amount", 0) or 0),
        "overdue_amount": float(r.get("overdue_amount", 0) or 0),
        "avg_aging_days": round(float(r.get("avg_aging_days", 0) or 0), 1),
        "touchless_rate": float(r.get("touchless_rate", 0) or 0),
    }


def get_payment_run_data() -> dict:
    """Get payment run summary."""
    if DEMO_MODE:
        return _get_payment_run_demo_data()
    rows = query(f"""
        SELECT
            COUNT(*) as total_payments,
            SUM(payment_amount_inr) as total_paid,
            AVG(days_to_pay) as avg_dpo,
            SUM(CASE WHEN payment_timing = 'EARLY' THEN 1 ELSE 0 END) as early_payments,
            SUM(CASE WHEN payment_timing = 'ON_TIME' THEN 1 ELSE 0 END) as on_time_payments,
            SUM(CASE WHEN payment_timing = 'LATE' THEN 1 ELSE 0 END) as late_payments
        FROM {full_table('gold_fact_payments')}
    """)
    if rows:
        r = rows[0]
        return {
            "total_payments": r.get("total_payments", 0),
            "total_paid": float(r.get("total_paid", 0) or 0),
            "avg_dpo": round(float(r.get("avg_dpo", 0) or 0), 1),
            "early_payments": r.get("early_payments", 0),
            "on_time_payments": r.get("on_time_payments", 0),
            "late_payments": r.get("late_payments", 0),
        }
    return {}


# ─── O2C Queries ─────────────────────────────────────────────

def get_collections(limit: int = 200) -> list[dict]:
    """Most recent customer invoices for the collections replay.

    auto_matched is derived from data: a cleared receipt exists in
    bronze_o2c_payments for the same invoice and for the invoice amount (±₹1).
    """
    return query(f"""
        WITH c AS (
            SELECT o2c_invoice_id, invoice_number, customer_id, customer_name, segment,
                   industry, invoice_date, due_date, invoice_total_inr,
                   amount_collected_inr, balance_outstanding, invoice_status,
                   aging_bucket, days_outstanding, days_overdue, is_fully_collected,
                   payment_method, region, legal_entity
            FROM {full_table('gold_fact_collections')}
        ),
        m AS (
            SELECT p.o2c_invoice_id,
                   MAX(CASE WHEN ABS(p.payment_amount - c.invoice_total_inr) <= 1 THEN 1 ELSE 0 END) = 1 AS auto_matched
            FROM {full_table('bronze_o2c_payments')} p
            JOIN c ON p.o2c_invoice_id = c.o2c_invoice_id
            GROUP BY p.o2c_invoice_id
        )
        SELECT c.*, COALESCE(m.auto_matched, false) AS auto_matched
        FROM c LEFT JOIN m ON c.o2c_invoice_id = m.o2c_invoice_id
        ORDER BY c.invoice_date DESC, c.o2c_invoice_id
        LIMIT {int(limit)}
    """)


def get_o2c_metrics() -> dict:
    """Get AR/O2C KPI metrics."""
    if DEMO_MODE:
        return _get_o2c_demo_metrics()

    aging = query(f"""
        SELECT aging_bucket, COUNT(*) as count, SUM(balance_outstanding) as amount
        FROM {full_table('gold_fact_collections')}
        WHERE balance_outstanding > 0
        GROUP BY aging_bucket
        ORDER BY
            CASE aging_bucket
                WHEN '0-30 days' THEN 1 WHEN '31-60 days' THEN 2
                WHEN '61-90 days' THEN 3 WHEN '90+ days' THEN 4 ELSE 5
            END
    """)

    totals = query(f"""
        SELECT
            SUM(balance_outstanding) as total_outstanding,
            AVG(CASE WHEN balance_outstanding > 0 THEN days_outstanding END) as avg_dso,
            COUNT(*) as total_invoices,
            SUM(CASE WHEN is_fully_collected = true THEN 1 ELSE 0 END) as collected,
            SUM(amount_collected_inr) as total_collected,
            SUM(invoice_total_inr) as total_billed,
            SUM(CASE WHEN days_overdue > 0 THEN 1 ELSE 0 END) as overdue_count
        FROM {full_table('gold_fact_collections')}
    """)

    customers_at_risk = query(f"""
        SELECT customer_name, credit_limit, outstanding_ar_inr,
               credit_utilization_pct, overdue_invoices, dso
        FROM {full_table('gold_dim_customer')}
        WHERE credit_utilization_pct > 80
        ORDER BY credit_utilization_pct DESC
        LIMIT 10
    """)

    if not totals:
        return {}
    t = totals[0]
    total_billed = float(t.get("total_billed", 0) or 0)
    total_collected = float(t.get("total_collected", 0) or 0)
    cei = round((total_collected / total_billed) * 100, 1) if total_billed else 0

    return {
        "total_outstanding": float(t.get("total_outstanding", 0) or 0),
        "avg_dso": round(float(t.get("avg_dso", 0) or 0), 1),
        "total_invoices": t.get("total_invoices", 0),
        "collected": t.get("collected", 0),
        "total_collected": total_collected,
        "overdue_count": t.get("overdue_count", 0),
        "cei": cei,
        "aging_buckets": [
            {"bucket": r["aging_bucket"], "count": r["count"], "amount": float(r["amount"] or 0)}
            for r in aging
        ],
        "customers_at_risk": [
            {
                "name": c["customer_name"],
                "credit_limit": float(c["credit_limit"] or 0),
                "outstanding": float(c["outstanding_ar_inr"] or 0),
                "utilization": float(c["credit_utilization_pct"] or 0),
                "overdue": c["overdue_invoices"],
                "dso": float(c["dso"] or 0),
            }
            for c in customers_at_risk
        ],
    }


# ─── R2R Queries ─────────────────────────────────────────────

def get_journal_entries(limit: int = 200) -> list[dict]:
    """Most recent GL lines (newest first; the stream replays them oldest first)."""
    return query(f"""
        SELECT je_id, je_number, gl_line_number, account_code, account_name,
               account_type, cost_center_name, department, je_date, period,
               je_type, status, posted_by, debit_inr, credit_inr,
               net_amount_inr, gl_description
        FROM {full_table('gold_fact_gl')}
        ORDER BY je_date DESC, je_id, gl_line_number
        LIMIT {int(limit)}
    """)


def shape_recon(rows: list[dict], items: list[dict]) -> dict:
    """Shape gold_recon_* rows for the UI.

    'Tied' is shown only when the UNEXPLAINED delta is zero (|Δ| < ₹1): the GL may
    legitimately differ from the sub-ledger by documented reconciling items.
    """
    by_acct: dict[str, list[dict]] = {}
    for it in items or []:
        by_acct.setdefault(str(it.get("account_code")), []).append({
            "document_id": it.get("document_id"),
            "document_type": it.get("document_type"),
            "amount": float(it.get("amount") or 0),
            "reason": it.get("reason"),
            "gl_je_id": it.get("gl_je_id"),
            "gl_je_status": it.get("gl_je_status"),
        })

    out = []
    for r in rows or []:
        sub = float(r.get("subledger_amount") or 0)
        gl = float(r.get("gl_amount") or 0)
        delta = float(r["delta"]) if r.get("delta") is not None else sub - gl
        explained = float(r.get("reconciling_items_amount") or 0)
        unexplained = (float(r["unexplained_delta"]) if r.get("unexplained_delta") is not None
                       else delta - explained)
        acct = str(r.get("account_code"))
        out.append({
            "account_code": acct,
            "account_name": r.get("account_name"),
            "subledger_source": r.get("subledger_source"),
            "subledger_amount": sub,
            "gl_amount": gl,
            "delta": delta,
            "reconciling_items_amount": explained,
            "reconciling_items_count": int(r.get("reconciling_items_count") or len(by_acct.get(acct, []))),
            "unexplained_delta": unexplained,
            # Never trust a stored flag over the arithmetic.
            "tied": abs(unexplained) < 1.0,
            "cutoff_date": str(r.get("cutoff_date")) if r.get("cutoff_date") is not None else None,
            "items": by_acct.get(acct, []),
        })
    return {"rows": out, "all_tied": bool(out) and all(x["tied"] for x in out)}


def get_subledger_gl_recon() -> dict:
    """Sub-ledger ↔ GL reconciliation with the documented reconciling items."""
    rows = query(f"""
        SELECT account_code, account_name, subledger_source, subledger_amount, gl_amount,
               delta, reconciling_items_amount, reconciling_items_count,
               unexplained_delta, tied, cutoff_date
        FROM {full_table('gold_recon_subledger_vs_gl')}
        ORDER BY account_code
    """)
    items = query(f"""
        SELECT account_code, document_id, document_type, amount, reason, gl_je_id, gl_je_status
        FROM {full_table('gold_recon_reconciling_items')}
        ORDER BY account_code, document_id
    """)
    return shape_recon(rows, items)


def get_r2r_metrics() -> dict:
    """Get GL/R2R KPI metrics."""
    if DEMO_MODE:
        return _get_r2r_demo_metrics()

    je_stats = query(f"""
        SELECT
            COUNT(DISTINCT je_id) as total_jes,
            COUNT(*) as total_lines,
            SUM(debit_inr) as total_debits,
            SUM(credit_inr) as total_credits,
            COUNT(DISTINCT CASE WHEN status = 'POSTED' THEN je_id END) as posted,
            COUNT(DISTINCT CASE WHEN status = 'PENDING' THEN je_id END) as pending
        FROM {full_table('gold_fact_gl')}
    """)

    latest = f"""(fiscal_year, period) = (
        SELECT fiscal_year, period FROM {full_table('gold_fact_trial_balance')}
        ORDER BY fiscal_year DESC, period DESC LIMIT 1)"""

    trial_balance = query(f"""
        SELECT account_code, account_name, account_type, account_subtype,
               closing_balance_inr, balance_type, period_debit, period_credit,
               period_net, transaction_count
        FROM {full_table('gold_fact_trial_balance')}
        WHERE {latest}
        ORDER BY account_code
    """)

    # A trial balance balances when Σ DR closing balances = Σ CR closing balances.
    tb_totals = query(f"""
        SELECT
            SUM(CASE WHEN balance_type = 'DR' THEN closing_balance_inr ELSE 0 END) as total_debit,
            SUM(CASE WHEN balance_type = 'CR' THEN closing_balance_inr ELSE 0 END) as total_credit
        FROM {full_table('gold_fact_trial_balance')}
        WHERE {latest}
    """)

    if not je_stats or not trial_balance:
        return {}
    j = je_stats[0]
    tb = tb_totals[0] if tb_totals else {}
    tb_dr = float(tb.get("total_debit", 0) or 0)
    tb_cr = float(tb.get("total_credit", 0) or 0)
    imbalance = abs(tb_dr - tb_cr)

    return {
        "total_jes": j.get("total_jes", 0),
        "total_lines": j.get("total_lines", 0),
        "total_debits": float(j.get("total_debits", 0) or 0),
        "total_credits": float(j.get("total_credits", 0) or 0),
        "posted": j.get("posted", 0),
        "pending": j.get("pending", 0),
        "tb_total_debit": tb_dr,
        "tb_total_credit": tb_cr,
        "tb_imbalance": imbalance,
        "is_balanced": imbalance < 1.0,
        "trial_balance": [
            {
                "account_code": r["account_code"],
                "account_name": r["account_name"],
                "account_type": r["account_type"],
                "debit": float(r["period_debit"] or 0),
                "credit": float(r["period_credit"] or 0),
                "balance": float(r["closing_balance_inr"] or 0),
                "balance_type": r["balance_type"],
                "transactions": r["transaction_count"],
            }
            for r in trial_balance
        ],
    }


def get_ap_exception_queue_from_warehouse(limit: int = 200, invoice_id: str | None = None) -> list[dict]:
    """Warehouse fallback for the AP exception queue (same shape as the Lakebase synced table)."""
    where = "WHERE i.invoice_id = %(invoice_id)s" if invoice_id else \
            "WHERE e.exception_type IS NOT NULL OR COALESCE(i.release_blocked, false)"
    return query(f"""
        SELECT i.invoice_id, i.invoice_number, i.vendor_id, i.vendor_name, i.legal_entity,
               i.invoice_date, i.due_date, i.invoice_total_inr, i.match_status,
               COALESCE(e.exception_type, CASE WHEN i.release_blocked THEN 'EXTRACTION_MISMATCH' END) AS exception_type,
               i.release_blocked, i.block_reason, i.ai_extracted_amount, i.pdf_file_path, i.aging_days
        FROM {full_table('gold_fact_invoices')} i
        LEFT JOIN {full_table('silver_invoice_exceptions')} e ON i.invoice_id = e.invoice_id
        {where}
        ORDER BY COALESCE(i.release_blocked, false) DESC, i.invoice_total_inr DESC
        LIMIT {int(limit)}
    """, {"invoice_id": invoice_id} if invoice_id else None)
