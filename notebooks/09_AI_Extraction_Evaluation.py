# Databricks notebook source
# MAGIC %md
# MAGIC # AI extraction evaluation (MLflow)
# MAGIC
# MAGIC Measures how well `ai_parse_document` + `ai_extract` (run inside the pipeline) read the invoice PDFs, and
# MAGIC how well the release-blocking control catches tampered invoices.
# MAGIC
# MAGIC **Ground truth.** What each PDF actually prints: the ERP record (`bronze_p2p_invoices` + vendor master)
# MAGIC for clean invoices, and the printed total from `silver_pdf_corruption_log` for the tampered ones.
# MAGIC
# MAGIC **Metrics.** Per-field accuracy (total, PO reference, GSTIN, invoice number, invoice date, due date),
# MAGIC tamper recall, tamper precision and the false-positive (clean invoice blocked) rate. Metrics and the
# MAGIC row-level evaluation table are logged to an MLflow experiment and appended to `gold_ai_extraction_eval`.

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower_catalog")
dbutils.widgets.text("schema", "finance_and_accounting")
dbutils.widgets.text("experiment", "")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
FQ = f"{CATALOG}.{SCHEMA}"

import json
import mlflow
from databricks.sdk import WorkspaceClient

me = WorkspaceClient().current_user.me().user_name
EXPERIMENT = dbutils.widgets.get("experiment") or f"/Users/{me}/fna_control_tower_ai_extraction_eval"
mlflow.set_experiment(EXPERIMENT)

# COMMAND ----------

eval_df = spark.sql(f"""
WITH erp AS (
  SELECT i.invoice_id, i.invoice_number, i.po_id, CAST(i.total_amount AS DOUBLE) AS erp_total,
         TO_DATE(i.invoice_date) AS invoice_date, TO_DATE(i.due_date) AS due_date, v.gstin AS vendor_gstin
  FROM {FQ}.bronze_p2p_invoices i
  LEFT JOIN {FQ}.bronze_vendors v ON i.vendor_id = v.vendor_id
),
norm AS (
  SELECT e.invoice_id,
         t.invoice_id IS NOT NULL                                   AS is_tampered,
         COALESCE(t.printed_total_inr, erp.erp_total)               AS printed_total,
         erp.erp_total,
         e.extracted_total_amount,
         upper(regexp_replace(erp.invoice_number, '[^A-Za-z0-9]', '')) AS t_invoice_number,
         upper(regexp_replace(e.extracted_invoice_number, '[^A-Za-z0-9]', '')) AS x_invoice_number,
         NULLIF(upper(regexp_replace(COALESCE(erp.po_id, ''), '[^A-Za-z0-9]', '')), '') AS t_po,
         NULLIF(upper(regexp_replace(COALESCE(e.extracted_po_reference, ''), '[^A-Za-z0-9]', '')), '') AS x_po,
         NULLIF(upper(regexp_replace(COALESCE(erp.vendor_gstin, ''), '[^A-Za-z0-9]', '')), '') AS t_gstin,
         NULLIF(upper(regexp_replace(COALESCE(e.extracted_gstin, ''), '[^A-Za-z0-9]', '')), '') AS x_gstin,
         erp.invoice_date AS t_invoice_date, e.extracted_invoice_date AS x_invoice_date,
         erp.due_date AS t_due_date, e.extracted_due_date AS x_due_date,
         COALESCE(s.release_blocked, false) AS release_blocked,
         s.block_reason, s.match_status
  FROM {FQ}.silver_invoice_extractions e
  JOIN erp ON e.invoice_id = erp.invoice_id
  LEFT JOIN {FQ}.silver_pdf_corruption_log t ON e.invoice_id = t.invoice_id
  LEFT JOIN {FQ}.silver_p2p_invoices s ON e.invoice_id = s.invoice_id
)
SELECT *,
  ABS(COALESCE(extracted_total_amount, -1) - printed_total) <= GREATEST(1.0, printed_total * 0.005) AS ok_total,
  (x_po <=> t_po)                                     AS ok_po,
  (x_gstin <=> t_gstin)                               AS ok_gstin,
  (x_invoice_number <=> t_invoice_number)             AS ok_invoice_number,
  (x_invoice_date <=> t_invoice_date)                 AS ok_invoice_date,
  (x_due_date <=> t_due_date)                         AS ok_due_date
FROM norm
""")
pdf = eval_df.toPandas()
n = len(pdf)
assert n > 0, "No extractions to evaluate: did the pipeline run?"

tampered = pdf[pdf.is_tampered]
clean = pdf[~pdf.is_tampered]
blocked = pdf[pdf.release_blocked]
metrics = {
    "documents_evaluated": n,
    "accuracy_total": round(pdf.ok_total.mean(), 4),
    "accuracy_po_reference": round(pdf.ok_po.mean(), 4),
    "accuracy_gstin": round(pdf.ok_gstin.mean(), 4),
    "accuracy_invoice_number": round(pdf.ok_invoice_number.mean(), 4),
    "accuracy_invoice_date": round(pdf.ok_invoice_date.mean(), 4),
    "accuracy_due_date": round(pdf.ok_due_date.mean(), 4),
    "tampered_documents": int(len(tampered)),
    "tampered_caught": int(tampered.release_blocked.sum()),
    "tamper_recall": round(float(tampered.release_blocked.mean()) if len(tampered) else 1.0, 4),
    "tamper_precision": round(float(blocked.is_tampered.mean()) if len(blocked) else 1.0, 4),
    "clean_blocked_false_positives": int(clean.release_blocked.sum()),
    "false_positive_rate": round(float(clean.release_blocked.mean()) if len(clean) else 0.0, 4),
}

with mlflow.start_run(run_name="ai_extraction_eval") as run:
    mlflow.log_params({"catalog": CATALOG, "schema": SCHEMA, "model": "ai_parse_document + ai_extract",
                       "total_tolerance": "max(1 INR, 0.5%)"})
    mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
    mlflow.log_table(pdf.drop(columns=[]).astype(str), artifact_file="eval_rows.json")
    run_id = run.info.run_id
metrics["mlflow_run_id"] = run_id
metrics["mlflow_experiment"] = EXPERIMENT

# COMMAND ----------

from pyspark.sql import functions as F
(spark.createDataFrame([(k, float(v)) for k, v in metrics.items() if isinstance(v, (int, float))], "metric STRING, value DOUBLE")
   .withColumn("mlflow_run_id", F.lit(run_id))
   .withColumn("evaluated_at", F.current_timestamp())
   .write.mode("append").option("mergeSchema", "true").saveAsTable(f"{FQ}.gold_ai_extraction_eval"))
spark.sql(f"COMMENT ON TABLE {FQ}.gold_ai_extraction_eval IS 'AI extraction evaluation metrics per MLflow run (notebook 09).'")

display(eval_df.filter("is_tampered OR release_blocked").select(
    "invoice_id", "is_tampered", "release_blocked", "block_reason", "printed_total", "erp_total", "extracted_total_amount", "match_status"))
print(json.dumps(metrics, indent=2))
dbutils.notebook.exit(json.dumps(metrics))
