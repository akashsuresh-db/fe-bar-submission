# Databricks notebook source
# MAGIC %md
# MAGIC # Teardown — drop the demo schema
# MAGIC
# MAGIC Drops `<catalog>.<schema>` with `CASCADE` (tables, views, volumes, functions). The catalog itself is
# MAGIC left in place because it is often a shared workspace catalog. Safe to re-run (`IF EXISTS`).

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower_catalog")
dbutils.widgets.text("schema", "finance_and_accounting")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

spark.sql(f"DROP SCHEMA IF EXISTS {CATALOG}.{SCHEMA} CASCADE")
print(f"Dropped schema {CATALOG}.{SCHEMA}")
