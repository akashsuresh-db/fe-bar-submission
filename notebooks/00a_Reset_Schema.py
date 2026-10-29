# Databricks notebook source
# MAGIC %md
# MAGIC # Reset raw landing zone (idempotent re-run guard)
# MAGIC
# MAGIC Creates the schema and the two landing volumes (`raw_csv`, `raw_invoices`) and clears every
# MAGIC file in them, so data generation starts from an empty landing zone. Pipeline-owned tables are
# MAGIC **not** dropped here: the setup job runs the pipeline with `full_refresh: true`, which rebuilds
# MAGIC every streaming table and materialized view from the freshly landed files.
# MAGIC
# MAGIC Errors are logged and re-raised. A failed reset must fail the job, not be silently skipped.

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower_catalog")
dbutils.widgets.text("schema", "finance_and_accounting")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

existing = [r[0] for r in spark.sql("SHOW CATALOGS").collect()]
if CATALOG not in existing:
    spark.sql(f"CREATE CATALOG {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
for vol in ("raw_csv", "raw_invoices"):
    spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{vol}")

# COMMAND ----------

import json

cleared = {}
for vol in ("raw_csv", "raw_invoices"):
    root = f"/Volumes/{CATALOG}/{SCHEMA}/{vol}"
    n = 0
    for entry in dbutils.fs.ls(root):
        try:
            dbutils.fs.rm(entry.path, recurse=True)
            n += 1
        except Exception as e:
            print(f"[reset] FAILED to remove {entry.path}: {e}")
            raise
    cleared[vol] = n
    print(f"[reset] cleared {n} entries from {root}")

dbutils.notebook.exit(json.dumps({"catalog": CATALOG, "schema": SCHEMA, "cleared": cleared}))
