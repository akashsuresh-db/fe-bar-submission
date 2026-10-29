"""Collect text-readable execution evidence from a deployed build into evidence/*.md.

Usage:
  python evidence/collect_evidence.py -p <profile> --warehouse <id> --catalog <cat> --schema <sch> \
      --pipeline-id <id> [--only kpi,recon,dq,lineage,governance]

Runs every query through the SQL Statement Execution API (Databricks CLI auth) and writes the SQL next to
its result, so each number in the README and deck can be traced to a query and its output.
"""
import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent


class Sql:
    def __init__(self, profile, warehouse):
        self.profile, self.warehouse = profile, warehouse

    def _cli(self, *args):
        out = subprocess.run(["databricks", *args, "-p", self.profile], capture_output=True, text=True)
        return json.loads(out.stdout or "{}")

    def run(self, statement):
        body = {"warehouse_id": self.warehouse, "statement": statement, "wait_timeout": "50s",
                "format": "JSON_ARRAY", "disposition": "INLINE"}
        r = self._cli("api", "post", "/api/2.0/sql/statements", "--json", json.dumps(body))
        while r.get("status", {}).get("state") in ("PENDING", "RUNNING"):
            time.sleep(3)
            r = self._cli("api", "get", f"/api/2.0/sql/statements/{r['statement_id']}")
        if r.get("status", {}).get("state") != "SUCCEEDED":
            return None, None, r.get("status", {}).get("error", {}).get("message", str(r))[:500]
        cols = [c["name"] for c in r["manifest"]["schema"]["columns"]]
        return cols, r.get("result", {}).get("data_array", []) or [], None


def md_table(cols, rows, limit=50):
    if cols is None:
        return ""
    def fmt(v):
        return "" if v is None else str(v).replace("|", "\\|").replace("\n", " ")[:120]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in rows[:limit]]
    if len(rows) > limit:
        out.append(f"\n_{len(rows) - limit} more rows not shown._")
    return "\n".join(out)


def section(sql, title, statement, limit=50):
    cols, rows, err = sql.run(statement)
    body = f"### {title}\n\n```sql\n{statement.strip()}\n```\n\n"
    body += f"**ERROR:** `{err}`\n" if err else md_table(cols, rows, limit) + "\n"
    return body, (cols, rows)


def write(name, title, parts, meta):
    text = f"# {title}\n\n_Collected {meta['ts']} from `{meta['host']}`, `{meta['fq']}`._\n\n" + "\n".join(parts)
    (HERE / name).write_text(text)
    print(f"wrote evidence/{name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--profile", required=True)
    ap.add_argument("--warehouse", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--pipeline-id", default="")
    ap.add_argument("--only", default="kpi,recon,dq,lineage,governance")
    a = ap.parse_args()
    fq = f"{a.catalog}.{a.schema}"
    sql = Sql(a.profile, a.warehouse)
    host = json.loads(subprocess.run(["databricks", "auth", "describe", "-p", a.profile, "-o", "json"],
                                     capture_output=True, text=True).stdout or "{}").get("details", {}).get("host", a.profile)
    meta = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "host": host, "fq": fq}
    only = set(a.only.split(","))

    if "kpi" in only:
        q = [
            ("Touchless rate (clean three-way match, not release-blocked)", f"""
SELECT COUNT(*) AS invoices,
       SUM(CASE WHEN match_status = 'THREE_WAY_MATCHED' THEN 1 ELSE 0 END) AS three_way_matched,
       SUM(CASE WHEN release_blocked THEN 1 ELSE 0 END) AS release_blocked,
       SUM(CASE WHEN is_touchless THEN 1 ELSE 0 END) AS touchless,
       ROUND(100 * AVG(CASE WHEN is_touchless THEN 1 ELSE 0 END), 1) AS touchless_pct
FROM {fq}.gold_fact_invoices"""),
            ("Exceptions by type (open work queue)", f"""
SELECT exception_type, COUNT(*) AS invoices, ROUND(SUM(total_amount) / 1e7, 2) AS value_inr_cr
FROM {fq}.silver_invoice_exceptions GROUP BY exception_type ORDER BY invoices DESC"""),
            ("Value held for review (all open exceptions)", f"""
SELECT COUNT(*) AS invoices, ROUND(SUM(invoice_total_inr) / 1e7, 2) AS value_inr_cr,
       SUM(CASE WHEN release_blocked THEN 1 ELSE 0 END) AS release_blocked
FROM {fq}.gold_ap_exception_queue"""),
            ("Duplicates blocked before payment", f"""
SELECT COUNT(*) AS duplicates, ROUND(SUM(total_amount) / 1e7, 2) AS value_inr_cr
FROM {fq}.silver_duplicate_invoices"""),
            ("Tampered PDFs caught by the AI control", f"""
SELECT t.invoice_id, t.true_total_inr, t.printed_total_inr, t.corruption_pct,
       i.release_blocked, i.block_reason, i.match_status
FROM {fq}.silver_pdf_corruption_log t LEFT JOIN {fq}.gold_fact_invoices i USING (invoice_id) ORDER BY t.invoice_id"""),
            ("Invoice GSTIN matches the vendor master (Indian vendors)", f"""
SELECT ROUND(100 * AVG(CASE WHEN i.gstin_vendor = v.gstin THEN 1 ELSE 0 END), 1) AS gstin_match_pct,
       SUM(CASE WHEN i.gstin_vendor IS NULL OR i.gstin_vendor = '' THEN 1 ELSE 0 END) AS invoices_missing_gstin,
       COUNT(*) AS invoices
FROM {fq}.gold_fact_invoices i JOIN {fq}.gold_dim_vendor v USING (vendor_id) WHERE v.country = 'India'"""),
            ("Accounts receivable: open balance, customers, average days outstanding", f"""
SELECT ROUND(SUM(balance_outstanding) / 1e7, 2) AS open_ar_inr_cr,
       COUNT(DISTINCT CASE WHEN balance_outstanding > 0 THEN customer_id END) AS customers_with_open_ar,
       ROUND(AVG(CASE WHEN balance_outstanding > 0 THEN days_outstanding END), 1) AS avg_days_outstanding,
       SUM(CASE WHEN aging_bucket = '90+ days' AND balance_outstanding > 0 THEN 1 ELSE 0 END) AS invoices_90_plus
FROM {fq}.gold_fact_collections"""),
            ("Accounts payable: open balance", f"""
SELECT ROUND(SUM(invoice_total_inr - paid_amount_inr) / 1e7, 2) AS open_ap_inr_cr, COUNT(*) AS invoices
FROM {fq}.gold_fact_invoices WHERE invoice_status != 'REJECTED'"""),
            ("Unbalanced journals quarantined", f"""
SELECT COUNT(*) AS journals, ROUND(SUM(imbalance_inr), 2) AS total_imbalance_inr FROM {fq}.silver_je_quarantine"""),
            ("AI extraction evaluation (latest MLflow run)", f"""
SELECT metric, value, mlflow_run_id FROM {fq}.gold_ai_extraction_eval
WHERE mlflow_run_id = (SELECT max_by(mlflow_run_id, evaluated_at) FROM {fq}.gold_ai_extraction_eval) ORDER BY metric"""),
            ("Row counts per governed table", f"""
SELECT table_name, table_type FROM {a.catalog}.information_schema.tables
WHERE table_schema = '{a.schema}' ORDER BY table_name"""),
        ]
        write("kpi_queries.md", "KPI queries and results", [section(sql, t, s)[0] for t, s in q], meta)

    if "recon" in only:
        q = [
            ("Trial balance: every period balances (expect 0 rows)", f"""
SELECT period, ROUND(SUM(CASE WHEN balance_type = 'DR' THEN closing_balance_inr ELSE -closing_balance_inr END), 2) AS net
FROM {fq}.gold_fact_trial_balance GROUP BY period HAVING ABS(net) > 1"""),
            ("Trial balance totals, latest period", f"""
SELECT period, ROUND(SUM(CASE WHEN balance_type = 'DR' THEN closing_balance_inr END) / 1e7, 4) AS dr_inr_cr,
       ROUND(SUM(CASE WHEN balance_type = 'CR' THEN closing_balance_inr END) / 1e7, 4) AS cr_inr_cr, COUNT(*) AS accounts
FROM {fq}.gold_fact_trial_balance WHERE period = (SELECT MAX(period) FROM {fq}.gold_fact_trial_balance) GROUP BY period"""),
            ("Sub-ledger vs GL reconciliation", f"SELECT * EXCEPT (_gold_processed_at) FROM {fq}.gold_recon_subledger_vs_gl ORDER BY account_code"),
            ("Reconciling items", f"SELECT * EXCEPT (_gold_processed_at) FROM {fq}.gold_recon_reconciling_items ORDER BY account_code"),
            ("GL postings by source module", f"""
SELECT source_module, COUNT(DISTINCT je_id) AS journals, ROUND(SUM(debit_inr) / 1e7, 2) AS debits_inr_cr
FROM {fq}.gold_fact_gl GROUP BY source_module ORDER BY source_module"""),
        ]
        write("F1_recon.md", "F1 — Reconciliation and trial balance", [section(sql, t, s)[0] for t, s in q], meta)

    if "dq" in only and a.pipeline_id:
        q = [
            ("Expectation pass/fail per rule (latest update)", f"""
WITH latest AS (SELECT origin.update_id AS u FROM event_log('{a.pipeline_id}') WHERE event_type = 'create_update' ORDER BY timestamp DESC LIMIT 1),
exp AS (
  SELECT origin.flow_name AS flow, explode(from_json(details:flow_progress:data_quality:expectations,
         'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) AS e
  FROM event_log('{a.pipeline_id}') WHERE event_type = 'flow_progress' AND origin.update_id = (SELECT u FROM latest)
    AND details:flow_progress:data_quality:expectations IS NOT NULL)
SELECT e.dataset, e.name AS expectation, SUM(e.passed_records) AS passed, SUM(e.failed_records) AS failed
FROM exp GROUP BY 1, 2 ORDER BY 1, 2"""),
            ("Pipeline updates", f"""
SELECT origin.update_id, timestamp, details:update_progress:state AS state
FROM event_log('{a.pipeline_id}') WHERE event_type = 'update_progress'
  AND details:update_progress:state IN ('COMPLETED', 'FAILED', 'CANCELED') ORDER BY timestamp DESC LIMIT 10"""),
        ]
        write("pipeline_event_log.md", "Pipeline event log — data quality", [section(sql, t, s, 80)[0] for t, s in q], meta)

    if "lineage" in only:
        q = [
            ("Table lineage within the schema (raw volumes → bronze → silver → gold → Lakebase synced table)", f"""
SELECT DISTINCT COALESCE(source_table_full_name, source_path) AS source, target_table_full_name AS target, entity_type
FROM system.access.table_lineage
WHERE (target_table_full_name LIKE '{fq}.%' OR source_table_full_name LIKE '{fq}.%')
  AND event_date >= current_date() - INTERVAL 2 DAYS
ORDER BY target, source""", 200),
        ]
        write("lineage.md", "Lineage — layers connected", [section(sql, *x)[0] if len(x) == 2 else section(sql, x[0], x[1], x[2])[0] for x in q], meta)

    if "governance" in only:
        q = [
            ("Grants on the schema", f"SHOW GRANTS ON SCHEMA {fq}"),
            ("Row filter and column masks", f"""
SELECT table_name, column_name, mask_name FROM {a.catalog}.information_schema.column_masks WHERE table_schema = '{a.schema}'
UNION ALL
SELECT table_name, filter_name, 'ROW FILTER on ' || target_columns FROM {a.catalog}.information_schema.row_filters WHERE table_schema = '{a.schema}'"""),
            ("Governed tags (table level)", f"""
SELECT table_name, tag_name, tag_value FROM {a.catalog}.information_schema.table_tags WHERE schema_name = '{a.schema}' ORDER BY 1, 2"""),
            ("Governed tags (PII columns)", f"""
SELECT table_name, column_name, tag_name, tag_value FROM {a.catalog}.information_schema.column_tags WHERE schema_name = '{a.schema}' ORDER BY 1, 2"""),
            ("Group to legal-entity map", f"SELECT * FROM {fq}.gov_entity_access"),
            ("As the presenter (member of finance_controllers): clear bank details, all entities", f"""
SELECT current_user() AS reader, is_member('finance_controllers') AS controller,
       (SELECT COUNT(DISTINCT legal_entity) FROM {fq}.gold_fact_invoices) AS entities_visible,
       (SELECT FIRST(extracted_bank_account) FROM {fq}.silver_invoice_extractions WHERE extracted_bank_account IS NOT NULL) AS sample_bank_account"""),
        ]
        write("F8_governance.md", "F8 — Unity Catalog governance", [section(sql, t, s, 80)[0] for t, s in q], meta)


if __name__ == "__main__":
    main()
