# Databricks notebook source
# MAGIC %md
# MAGIC # Lakebase operational serving and write-back
# MAGIC
# MAGIC 1. **Gold → Lakebase.** Ensures the Postgres database exists, then creates (or refreshes) the synced table
# MAGIC    `<catalog>.<schema>.ap_exception_queue` from `gold_ap_exception_queue`. Postgres serves it as
# MAGIC    `"<schema>"."ap_exception_queue"`; the app's AP queue and exception drawer read it at OLTP latency.
# MAGIC 2. **Lakebase → Unity Catalog.** Copies the app's operational writes (`fna_app.ap_approvals`, `fna_app.ar_call_logs`,
# MAGIC    `fna_app.chat_history`) into `ops_*` Delta tables, so Genie and the Gold KPIs can count approvals and
# MAGIC    promises-to-pay. (Registering the database as a UC catalog needs `CREATE CATALOG` on the metastore,
# MAGIC    which the FEVM workspace does not grant; this task is the documented substitute.)

# COMMAND ----------

# MAGIC %pip install "psycopg[binary]>=3.2" --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower_catalog")
dbutils.widgets.text("schema", "finance_and_accounting")
dbutils.widgets.text("instance_name", "finance-ops-db")
dbutils.widgets.text("database_name", "finance_ops_app")
dbutils.widgets.dropdown("mode", "all", ["all", "sync", "writeback"])
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
INSTANCE = dbutils.widgets.get("instance_name")
DATABASE = dbutils.widgets.get("database_name")
MODE = dbutils.widgets.get("mode")
FQ = f"{CATALOG}.{SCHEMA}"
APP_SCHEMA = "fna_app"  # Postgres schema owned by the app (app/backend/lakebase.py)

import json, time, uuid
import psycopg
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.database import (
    SyncedDatabaseTable, SyncedTableSpec, SyncedTableSchedulingPolicy, NewPipelineSpec)

w = WorkspaceClient()
me = w.current_user.me().user_name
inst = w.database.get_database_instance(INSTANCE)
report = {"instance": INSTANCE, "database": DATABASE, "host": inst.read_write_dns}


def pg(dbname):
    token = w.database.generate_database_credential(request_id=str(uuid.uuid4()), instance_names=[INSTANCE]).token
    return psycopg.connect(host=inst.read_write_dns, port=5432, dbname=dbname, user=me,
                           password=token, sslmode="require", autocommit=True)

# COMMAND ----------

# MAGIC %md ## 1. Gold → Lakebase synced table

# COMMAND ----------

SYNCED = f"{FQ}.ap_exception_queue"
if MODE in ("all", "sync"):
    conn = pg("databricks_postgres")
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{DATABASE}"')
            print(f"[lakebase] created database {DATABASE}")
    conn.close()

    try:
        st = w.database.get_synced_database_table(SYNCED)
        pipeline_id = st.data_synchronization_status.pipeline_id
        w.pipelines.start_update(pipeline_id=pipeline_id)
        action = "refreshed"
    except Exception as e:
        if "does not exist" not in str(e).lower() and "not found" not in str(e).lower():
            raise
        st = w.database.create_synced_database_table(SyncedDatabaseTable(
            name=SYNCED, database_instance_name=INSTANCE, logical_database_name=DATABASE,
            spec=SyncedTableSpec(
                source_table_full_name=f"{FQ}.gold_ap_exception_queue",
                primary_key_columns=["invoice_id"],
                scheduling_policy=SyncedTableSchedulingPolicy.SNAPSHOT,
                create_database_objects_if_missing=True,
                new_pipeline_spec=NewPipelineSpec(storage_catalog=CATALOG, storage_schema=SCHEMA))))
        action = "created"
    # Wait for the snapshot to land, then count rows in Postgres
    rows, last = None, ""
    for _ in range(60):
        try:
            conn = pg(DATABASE)
            with conn.cursor() as cur:
                cur.execute(f'SELECT COUNT(*) FROM "{SCHEMA}"."ap_exception_queue"')
                rows = cur.fetchone()[0]
            conn.close()
            if rows:
                break
        except Exception as e:
            last = str(e)[:150]
        time.sleep(20)
    # The app's Postgres role reads the synced queue; instance access itself is governed by Databricks permissions
    conn = pg(DATABASE)
    with conn.cursor() as cur:
        cur.execute(f'GRANT USAGE ON SCHEMA "{SCHEMA}" TO PUBLIC')
        cur.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{SCHEMA}" TO PUBLIC')
    conn.close()
    report.update({"synced_table": SYNCED, "synced_action": action,
                   "postgres_table": f'"{SCHEMA}"."ap_exception_queue"', "postgres_rows": rows})
    if not rows:
        raise RuntimeError(f"Synced table has no rows in Postgres after waiting: {last if rows is None else 0}")
    print(json.dumps(report, indent=2))

# COMMAND ----------

# MAGIC %md ## 2. Lakebase → Unity Catalog write-back

# COMMAND ----------

import pandas as pd

if MODE in ("all", "writeback"):
    copied = {}
    conn = pg(DATABASE)
    for table in ("ap_approvals", "ar_call_logs", "chat_history"):
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (f"{APP_SCHEMA}.{table}",))
            if cur.fetchone()[0] is None:
                copied[table] = "not created yet (app has not started)"
                continue
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {APP_SCHEMA}.{table}")
            df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        target = f"{FQ}.ops_{table}"
        if len(df):
            sdf = spark.createDataFrame(df.astype(object).where(df.notna(), None))
            sdf.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(target)
        else:
            spark.sql(f"CREATE TABLE IF NOT EXISTS {target} (placeholder STRING)")
        spark.sql(f"COMMENT ON TABLE {target} IS 'Copied from Lakebase {DATABASE}.{APP_SCHEMA}.{table} by 10_Lakebase_Sync.'")
        copied[table] = len(df)
    conn.close()
    report["writeback_rows"] = copied
    print(json.dumps(report, indent=2))

dbutils.notebook.exit(json.dumps(report, default=str))
