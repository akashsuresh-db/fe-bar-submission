# Databricks notebook source
# MAGIC %md
# MAGIC # Drop DLT-owned bronze tables (staging handoff)
# MAGIC
# MAGIC Data generation (`00`) and PDF generation (`01a`) write `bronze_*` **managed**
# MAGIC tables as a staging step; `00b` exports the transactional ones to `/raw_csv/`.
# MAGIC The DLT pipeline (`01`) then re-materialises the same `bronze_*` names from those
# MAGIC CSVs / the invoice volume. On a fresh schema those names collide ("Could not
# MAGIC materialize … a MANAGED table already exists"). This task drops **only** the
# MAGIC bronze tables the DLT pipeline owns, so DLT can create them. Non-DLT bronze
# MAGIC tables (po_line, so_lines, chart_of_accounts, cost_centers, je_lines,
# MAGIC o2c_payments) are preserved for the gold notebooks.

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower_catalog")
dbutils.widgets.text("schema", "finance_and_accounting")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

# Tables the DLT pipeline (notebooks/01_DLT_Pipeline.py) declares via @dlt.table.
DLT_OWNED_BRONZE = [
    "bronze_vendors",
    "bronze_customers",
    "bronze_po_header",
    "bronze_grn",
    "bronze_p2p_invoices",
    "bronze_p2p_payments",
    "bronze_sales_orders",
    "bronze_o2c_invoices",
    "bronze_journal_entries",
    "bronze_raw_invoice_documents",
]

for t in DLT_OWNED_BRONZE:
    spark.sql(f"DROP TABLE IF EXISTS {CATALOG}.{SCHEMA}.{t}")
    print(f"[cleanup] dropped {CATALOG}.{SCHEMA}.{t}")

print(f"[cleanup] {len(DLT_OWNED_BRONZE)} DLT-owned bronze tables cleared — DLT can now materialise them.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Bootstrap silver_invoice_extractions
# MAGIC The DLT flow `silver_p2p_invoices` LEFT-joins `silver_invoice_extractions`, which is
# MAGIC produced later by notebook 05 (AI extraction). On the very first pipeline run that
# MAGIC table does not exist yet, so DLT fails to *analyze* the flow
# MAGIC (`TABLE_OR_VIEW_NOT_FOUND`). Create it empty (with the columns the flow reads) so the
# MAGIC first DLT run resolves; notebook 05 later overwrites it with the real AI extractions
# MAGIC and the `dlt_refresh_with_extractions` task re-materialises gold with that data.

# COMMAND ----------

spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.silver_invoice_extractions (
        invoice_id STRING,
        vendor_id STRING,
        file_path STRING,
        extracted_vendor_name STRING,
        extracted_gstin STRING,
        extracted_total_amount DOUBLE
    ) USING DELTA
""")
print(f"[cleanup] ensured {CATALOG}.{SCHEMA}.silver_invoice_extractions exists (DLT bootstrap)")
