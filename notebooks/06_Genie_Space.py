# Databricks notebook source
# MAGIC %md
# MAGIC # Genie Agent — create or update the Finance Control Tower space
# MAGIC
# MAGIC Idempotent: finds the space by title and updates it, otherwise creates it. The space covers the Gold,
# MAGIC exception, reconciliation and AI-evaluation tables, the curated instructions in `genie_instructions.md`,
# MAGIC sample questions and example SQL. The space id is returned with `dbutils.notebook.exit`, so
# MAGIC `setup/setup.sh` can pass it to the app (`--var genie_space_id=<id>`).

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower_catalog")
dbutils.widgets.text("schema", "finance_and_accounting")
dbutils.widgets.text("warehouse_id", "")
dbutils.widgets.text("title", "Finance Operations Control Tower")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id")
TITLE = dbutils.widgets.get("title")
FQ = f"{CATALOG}.{SCHEMA}"
assert WAREHOUSE_ID, "warehouse_id is required"

import json, os, hashlib
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# COMMAND ----------

TABLES = [
    "gold_ai_extraction_eval", "gold_ap_exception_queue", "gold_dim_customer", "gold_dim_vendor",
    "gold_fact_collections", "gold_fact_gl", "gold_fact_invoices", "gold_fact_payments", "gold_fact_sales",
    "gold_fact_trial_balance", "gold_recon_reconciling_items", "gold_recon_subledger_vs_gl",
    "silver_invoice_exceptions",
]

SAMPLE_QUESTIONS = [
    "What is our touchless invoice rate?",
    "Which invoices were blocked because the PDF disagrees with the ERP?",
    "Do AR and AP tie to the general ledger, and what explains any difference?",
    "Which customers have the most overdue receivables?",
    "Show open AP exceptions by type and value",
    "How accurate is the AI invoice extraction?",
]

EXAMPLE_SQL = [
    ("What is our touchless invoice rate?",
     f"SELECT ROUND(100 * AVG(CASE WHEN is_touchless THEN 1 ELSE 0 END), 1) AS touchless_pct, COUNT(*) AS invoices FROM {FQ}.gold_fact_invoices"),
    ("Which invoices were blocked because the PDF disagrees with the ERP?",
     f"SELECT invoice_id, vendor_name, invoice_total_inr, ai_extracted_amount, block_reason FROM {FQ}.gold_fact_invoices WHERE release_blocked ORDER BY invoice_total_inr DESC"),
    ("Do AR and AP tie to the general ledger?",
     f"SELECT account_code, account_name, subledger_amount, gl_amount, delta, reconciling_items_amount, unexplained_delta, tied FROM {FQ}.gold_recon_subledger_vs_gl ORDER BY account_code"),
    ("What explains the reconciliation difference?",
     f"SELECT account_code, document_id, document_type, amount, reason, gl_je_status FROM {FQ}.gold_recon_reconciling_items ORDER BY account_code, amount DESC"),
    ("How accurate is the AI invoice extraction?",
     f"SELECT metric, value FROM {FQ}.gold_ai_extraction_eval WHERE mlflow_run_id = (SELECT max_by(mlflow_run_id, evaluated_at) FROM {FQ}.gold_ai_extraction_eval) ORDER BY metric"),
]


def hid(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


instructions = open(os.path.join(os.getcwd(), "genie_instructions.md")).read()
instructions = instructions.replace("{catalog}", CATALOG).replace("{schema}", SCHEMA)

space = {
    "version": 2,
    "config": {"sample_questions": sorted([{"id": hid("q" + q), "question": [q]} for q in SAMPLE_QUESTIONS],
                                          key=lambda x: x["id"])},
    "data_sources": {"tables": [{"identifier": f"{FQ}.{t}"} for t in sorted(TABLES)]},
    "instructions": {
        "text_instructions": [{"id": hid("instructions"), "content": [instructions]}],
        "example_question_sqls": sorted([{"id": hid("x" + q), "question": [q], "sql": [sql]} for q, sql in EXAMPLE_SQL],
                                        key=lambda x: x["id"]),
    },
}
payload = {"title": TITLE, "warehouse_id": WAREHOUSE_ID, "serialized_space": json.dumps(space),
           "description": "Natural-language analytics over the governed P2P, O2C and R2R tables of the Finance Operations Control Tower."}

# COMMAND ----------

existing, token = None, None
while True:
    resp = w.api_client.do("GET", "/api/2.0/genie/spaces", query={"page_size": 100, **({"page_token": token} if token else {})})
    for sp in resp.get("spaces", []):
        if sp.get("title") == TITLE:
            existing = sp["space_id"]
    token = resp.get("next_page_token")
    if existing or not token:
        break

if existing:
    w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{existing}", body=payload)
    space_id, action = existing, "updated"
else:
    space_id = w.api_client.do("POST", "/api/2.0/genie/spaces", body=payload)["space_id"]
    action = "created"

out = {"space_id": space_id, "action": action, "tables": len(TABLES),
       "url": f"{w.config.host}/genie/rooms/{space_id}"}
print(json.dumps(out, indent=2))
dbutils.notebook.exit(json.dumps(out))
