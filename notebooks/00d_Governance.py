# Databricks notebook source
# MAGIC %md
# MAGIC # Unity Catalog governance
# MAGIC
# MAGIC Runs twice in the setup job:
# MAGIC
# MAGIC | Phase | When | What |
# MAGIC |---|---|---|
# MAGIC | `pre` | before the pipeline | Finance groups, the group → legal-entity map, the row-filter function and the column-mask functions. The pipeline attaches them to `gold_fact_invoices`, `gold_fact_collections` (row filter on `legal_entity`) and `silver_invoice_extractions` (masks on bank account, IFSC and GSTIN). |
# MAGIC | `post` | after the pipeline | Governed tags (`domain`, `pii`) and least-privilege grants (`USE CATALOG`, `USE SCHEMA`, `SELECT`; never `ALL PRIVILEGES`). |
# MAGIC
# MAGIC Access model:
# MAGIC - `finance_controllers` see every legal entity and clear bank details.
# MAGIC - `ap_analysts_in` / `ap_analysts_uk` see only their entity's invoices and collections, with masked bank details.
# MAGIC
# MAGIC The groups are workspace-local groups (FEVM workspaces cannot create account groups), so the functions
# MAGIC use `is_member()`. With account groups, swap in `is_account_group_member()`.

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower_catalog")
dbutils.widgets.text("schema", "finance_and_accounting")
dbutils.widgets.dropdown("phase", "pre", ["pre", "post"])
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
PHASE = dbutils.widgets.get("phase")
FQ = f"{CATALOG}.{SCHEMA}"

import json
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import iam

w = WorkspaceClient()
me = w.current_user.me()
report = {"phase": PHASE, "catalog": CATALOG, "schema": SCHEMA}
ENTITY_GROUPS = {"ap_analysts_in": "MERIDIAN-IN", "ap_analysts_uk": "MERIDIAN-UK"}
GROUPS = ["finance_controllers", *ENTITY_GROUPS]

# COMMAND ----------

# MAGIC %md ## Phase `pre`: groups, entity map, row filter and masks

# COMMAND ----------

if PHASE == "pre":
    existing = {g.display_name: g for g in w.groups.list(attributes="id,displayName")}
    for name in GROUPS:
        if name not in existing:
            existing[name] = w.groups.create(display_name=name)
            print(f"[gov] created group {name}")
    # The job owner (the demo presenter) is a finance controller
    w.groups.patch(existing["finance_controllers"].id,
                   operations=[iam.Patch(op=iam.PatchOp.ADD, path="members", value=[{"value": me.id}])],
                   schemas=[iam.PatchSchema.URN_IETF_PARAMS_SCIM_API_MESSAGES_2_0_PATCH_OP])
    report["groups"] = GROUPS

    spark.sql(f"""
        CREATE OR REPLACE TABLE {FQ}.gov_entity_access (group_name STRING, legal_entity STRING)
        COMMENT 'Maps finance groups to the legal entities whose rows they may read (used by rf_legal_entity).'
    """)
    rows = ", ".join(f"('{g}', '{e}')" for g, e in ENTITY_GROUPS.items())
    spark.sql(f"INSERT INTO {FQ}.gov_entity_access VALUES {rows}")

    spark.sql(f"""
        CREATE OR REPLACE FUNCTION {FQ}.rf_legal_entity(entity STRING)
        RETURN is_member('finance_controllers')
            OR EXISTS (SELECT 1 FROM {FQ}.gov_entity_access a
                       WHERE a.legal_entity = entity AND is_member(a.group_name))
    """)
    spark.sql(f"""
        CREATE OR REPLACE FUNCTION {FQ}.mask_bank_account(v STRING)
        RETURN CASE WHEN is_member('finance_controllers') OR v IS NULL THEN v
                    ELSE concat('XXXX', right(v, 4)) END
    """)
    spark.sql(f"""
        CREATE OR REPLACE FUNCTION {FQ}.mask_gstin(v STRING)
        RETURN CASE WHEN is_member('finance_controllers') OR v IS NULL THEN v
                    ELSE concat(left(v, 2), 'XXXXXXXX', right(v, 3)) END
    """)
    report["functions"] = ["rf_legal_entity", "mask_bank_account", "mask_gstin"]
    print(json.dumps(report, indent=2))

# COMMAND ----------

# MAGIC %md ## Phase `post`: governed tags and least-privilege grants

# COMMAND ----------

DOMAIN_TAGS = {
    "P2P": ["bronze_vendors", "bronze_p2p_invoices", "silver_p2p_invoices", "silver_invoice_extractions",
            "silver_invoice_exceptions", "silver_duplicate_invoices", "gold_dim_vendor", "gold_fact_invoices",
            "gold_fact_payments", "gold_ap_exception_queue"],
    "O2C": ["bronze_customers", "silver_o2c_invoices", "gold_dim_customer", "gold_fact_sales", "gold_fact_collections"],
    "R2R": ["bronze_journal_entries", "bronze_je_lines", "silver_je_quarantine", "gold_fact_gl", "gold_fact_trial_balance",
            "gold_recon_subledger_vs_gl", "gold_recon_reconciling_items"],
}
PII_COLUMNS = {
    "silver_invoice_extractions": ["extracted_bank_account", "extracted_ifsc", "extracted_gstin"],
    "bronze_vendors": ["bank_account", "bank_ifsc", "gstin", "contact_email"],
    "bronze_customers": ["gstin", "contact_email"],
    "gold_dim_vendor": ["gstin"],
    "gold_fact_invoices": ["gstin_vendor"],
}


def table_kind(name):
    t = spark.sql(f"DESCRIBE TABLE EXTENDED {FQ}.{name}").filter("col_name = 'Type'").collect()
    kind = t[0]["data_type"].upper() if t else "MANAGED"
    return "MATERIALIZED VIEW" if "MATERIALIZED" in kind else ("STREAMING TABLE" if "STREAMING" in kind else "TABLE")


def alter(name, clause):
    kind = table_kind(name)
    spark.sql(f"ALTER {kind} {FQ}.{name} {clause}")


if PHASE == "post":
    tagged, failures = [], []
    for domain, tables in DOMAIN_TAGS.items():
        for t in tables:
            try:
                alter(t, f"SET TAGS ('domain' = '{domain}', 'project' = 'finance_ops_control_tower')")
                tagged.append(t)
            except Exception as e:
                failures.append({"table": t, "error": str(e)[:200]})
    pii = []
    for t, cols in PII_COLUMNS.items():
        for c in cols:
            try:
                alter(t, f"ALTER COLUMN {c} SET TAGS ('pii' = 'true')")
                pii.append(f"{t}.{c}")
            except Exception as e:
                failures.append({"table": f"{t}.{c}", "error": str(e)[:200]})

    grants = []
    for g in GROUPS:
        for stmt in (f"GRANT USE CATALOG ON CATALOG {CATALOG} TO `{g}`",
                     f"GRANT USE SCHEMA ON SCHEMA {FQ} TO `{g}`",
                     f"GRANT SELECT ON SCHEMA {FQ} TO `{g}`",
                     f"GRANT READ VOLUME ON VOLUME {FQ}.raw_invoices TO `{g}`"):
            try:
                spark.sql(stmt)
                grants.append(stmt)
            except Exception as e:
                failures.append({"grant": stmt, "error": str(e)[:200]})
    report.update({"tagged_tables": len(tagged), "pii_columns": pii, "grants": grants, "failures": failures})
    print(json.dumps(report, indent=2))
    if len(tagged) == 0:
        raise RuntimeError(f"No table could be tagged: {failures[:3]}")

dbutils.notebook.exit(json.dumps(report))
