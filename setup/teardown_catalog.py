# Databricks notebook source
# MAGIC %md
# MAGIC # Teardown — Drop demo catalog
# MAGIC
# MAGIC Removes the Unity Catalog objects created by setup (schemas, tables, volumes).
# MAGIC `DROP CATALOG ... CASCADE` leaves no orphans. Safe to re-run (`IF EXISTS`).
# MAGIC Referenced by the `fna_teardown_job` in `resources/jobs.yml`; the bundle's own
# MAGIC resources (jobs, pipeline, app) are removed separately by `databricks bundle destroy`.

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower_catalog")
dbutils.widgets.text("schema", "finance_and_accounting")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

print(f"Dropping catalog {CATALOG} (CASCADE) — removes {CATALOG}.{SCHEMA} and all tables/volumes...")
spark.sql(f"DROP CATALOG IF EXISTS {CATALOG} CASCADE")
print("Teardown complete: catalog dropped (or already absent).")
