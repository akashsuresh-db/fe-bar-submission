# Databricks notebook source
# MAGIC %md
# MAGIC # Reset schema (idempotent re-run guard)
# MAGIC
# MAGIC On a re-run the DLT pipeline has already turned `bronze_*` (and silver/gold)
# MAGIC into **streaming tables / materialized views**, which the data-generation
# MAGIC notebook cannot `CREATE OR REPLACE` (`STREAMING_TABLE_OPERATION_NOT_ALLOWED`).
# MAGIC This task drops every table/view in the demo schema so the build starts clean.
# MAGIC Volumes (raw_invoices, raw_csv) are left intact and re-created `IF NOT EXISTS`.

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower_catalog")
dbutils.widgets.text("schema", "finance_and_accounting")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

try:
    objs = [r["tableName"] for r in spark.sql(f"SHOW TABLES IN {CATALOG}.{SCHEMA}").collect()]
except Exception as e:
    print(f"[reset] schema not queryable yet ({e}) — nothing to drop")
    objs = []

dropped = 0
for name in objs:
    fq = f"{CATALOG}.{SCHEMA}.`{name}`"
    for stmt in (
        f"DROP MATERIALIZED VIEW IF EXISTS {fq}",
        f"DROP VIEW IF EXISTS {fq}",
        f"DROP TABLE IF EXISTS {fq}",
    ):
        try:
            spark.sql(stmt)
            dropped += 1
            print(f"[reset] dropped {name}")
            break
        except Exception:
            continue

print(f"[reset] cleared {dropped} object(s) from {CATALOG}.{SCHEMA}")
