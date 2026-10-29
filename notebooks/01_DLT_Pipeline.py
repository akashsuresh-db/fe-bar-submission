# Databricks notebook source
# MAGIC %md
# MAGIC # Finance & Accounting declarative pipeline — Bronze → Silver → Gold
# MAGIC
# MAGIC **Bronze** ingests every ERP extract with Auto Loader (`cloudFiles`) from `/Volumes/{catalog}/{schema}/raw_csv/<entity>/`
# MAGIC and the invoice PDFs from `/raw_invoices/`. No table in this pipeline is read by name with `spark.table`:
# MAGIC every dependency is a `dlt.read` / `dlt.read_stream`, so a full refresh on an empty schema builds cleanly.
# MAGIC
# MAGIC **AI extraction runs inside the pipeline.** `silver_invoice_extractions` applies `ai_parse_document` and
# MAGIC `ai_extract` to each PDF once (streaming table), and `silver_p2p_invoices` compares the extracted total,
# MAGIC GSTIN and PO reference with the ERP. Any disagreement sets `release_blocked = true`, so a tampered invoice
# MAGIC can never be paid touchless.
# MAGIC
# MAGIC **Exceptions** (`silver_invoice_exceptions`), highest severity first: `DUPLICATE`, `EXTRACTION_MISMATCH`,
# MAGIC `NO_PO_REFERENCE`, `AMOUNT_MISMATCH`, `MISSING_GRN`, `MISSING_GSTIN`, `CRITICAL_OVERDUE`, `PENDING_REVIEW`.
# MAGIC
# MAGIC **Gold** builds the P2P, O2C and R2R facts in this pipeline. The general ledger is derived from journal
# MAGIC lines (which the ERP posts from the sub-ledgers); the trial balance balances in every period, and
# MAGIC `gold_recon_subledger_vs_gl` compares the sub-ledgers with the GL control accounts and explains the delta
# MAGIC with `gold_recon_reconciling_items`.
# MAGIC
# MAGIC **Governance.** When the pipeline configuration sets `governance = true`, the invoice and collections facts
# MAGIC carry a row filter on `legal_entity`, and the AI-extracted bank details and GSTIN are column-masked. The
# MAGIC functions are created by `00d_Governance.py` before the pipeline runs.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# DLT reads config from the pipeline `configuration` block (set by the bundle);
# defaults keep the notebook runnable interactively.
CATALOG = spark.conf.get("catalog", "fna_control_tower_catalog")
SCHEMA = spark.conf.get("schema", "finance_and_accounting")
RAW_CSV = f"/Volumes/{CATALOG}/{SCHEMA}/raw_csv"
GOVERNANCE = spark.conf.get("governance", "false").lower() == "true"
FQ = f"{CATALOG}.{SCHEMA}"
ROW_FILTER = f"ROW FILTER {FQ}.rf_legal_entity ON (legal_entity)" if GOVERNANCE else None
MASK_BANK = f" MASK {FQ}.mask_bank_account" if GOVERNANCE else ""
MASK_GSTIN = f" MASK {FQ}.mask_gstin" if GOVERNANCE else ""


# ─── Business expectation predicates (SINGLE SOURCE OF TRUTH) ───────────────
# Each predicate is used in TWO places:
#   1) @dlt.expect decorator on silver_p2p_invoices  → shows up in the DLT Data
#      Quality tab with non-zero failed_records counts.
#   2) The CASE WHEN in silver_invoice_exceptions    → drives the UI's exception
#      type column.
# If a rule changes, change it here only. Do not duplicate logic anywhere else.
EXPECT_HAS_PO_REFERENCE       = "po_id IS NOT NULL AND po_id != ''"
EXPECT_AMOUNT_MATCHES_PO      = "po_total_amount IS NULL OR ABS(invoice_amount - po_total_amount) < invoice_amount * 0.05"
EXPECT_HAS_GRN                = "COALESCE(grn_count, 0) > 0"
EXPECT_HAS_VENDOR_GSTIN       = "COALESCE(vendor_country, 'India') != 'India' OR (gstin_vendor IS NOT NULL AND gstin_vendor != '')"
EXPECT_NOT_CRITICALLY_OVERDUE = "status IN ('PAID', 'REJECTED') OR datediff(current_date(), due_date) <= 60"
# AI extraction controls. The PDF prints the tax-inclusive total, so it is compared with total_amount
# (not the pre-tax invoice_amount). 0.5% tolerance absorbs rounding; every seeded tamper is >= 3%.
EXPECT_EXTRACTION_MATCHES_ERP = "ai_extracted_amount IS NULL OR ABS(ai_extracted_amount - total_amount) <= GREATEST(1.0, total_amount * 0.005)"
EXPECT_EXTRACTED_GSTIN_MATCHES = "ai_gstin_norm IS NULL OR erp_gstin_norm IS NULL OR ai_gstin_norm = erp_gstin_norm"
EXPECT_EXTRACTED_PO_MATCHES    = "ai_po_norm IS NULL OR erp_po_norm IS NULL OR ai_po_norm = erp_po_norm"


def _norm_id(col):
    """Upper-case alphanumerics only; empty and N/A-style values become NULL."""
    v = F.upper(F.regexp_replace(F.col(col).cast("string"), r"[^A-Za-z0-9]", ""))
    return F.when(v.isin("", "NA", "NONE", "NULL", "NIL"), None).otherwise(v)


def autoload_csv(entity: str):
    """Auto Loader stream from a CSV-per-entity folder under /raw_csv/."""
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.inferColumnTypes", "true")
        .option("header", "true")
        .option("multiLine", "true")
        .option("escape", '"')
        .load(f"{RAW_CSV}/{entity}/")
    )

# COMMAND ----------

# MAGIC %md ## BRONZE LAYER — Auto Loader ingestion from raw CSV

# COMMAND ----------

@dlt.table(name="bronze_vendors", comment="Vendor master — Auto Loader from /raw_csv/vendors/",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_csv"})
@dlt.expect_or_drop("valid_vendor_id", "vendor_id IS NOT NULL")
@dlt.expect_or_drop("valid_vendor_name", "vendor_name IS NOT NULL AND LENGTH(vendor_name) > 0")
@dlt.expect("valid_email", "contact_email LIKE '%@%'")
def bronze_vendors():
    return autoload_csv("vendors")


@dlt.table(name="bronze_customers", comment="Customer master — Auto Loader from /raw_csv/customers/",
           table_properties={"quality": "bronze", "domain": "O2C", "source": "raw_csv"})
@dlt.expect_or_drop("valid_customer_id", "customer_id IS NOT NULL")
@dlt.expect_or_drop("valid_customer_name", "customer_name IS NOT NULL")
def bronze_customers():
    return autoload_csv("customers")


@dlt.table(name="bronze_po_header", comment="Purchase orders — Auto Loader from /raw_csv/po_header/",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_csv"})
@dlt.expect_or_drop("valid_po_id", "po_id IS NOT NULL")
@dlt.expect_or_drop("valid_vendor_ref", "vendor_id IS NOT NULL")
@dlt.expect("positive_amount", "total_amount > 0")
def bronze_po_header():
    return autoload_csv("po_header")


@dlt.table(name="bronze_grn", comment="Goods receipts — Auto Loader from /raw_csv/grn/",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_csv"})
@dlt.expect_or_drop("valid_grn_id", "grn_id IS NOT NULL")
@dlt.expect_or_drop("valid_po_ref", "po_id IS NOT NULL")
def bronze_grn():
    return autoload_csv("grn")


@dlt.table(name="bronze_p2p_invoices", comment="Vendor invoices — Auto Loader from /raw_csv/p2p_invoices/",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_csv"})
@dlt.expect_or_drop("valid_invoice_id", "invoice_id IS NOT NULL")
@dlt.expect_or_drop("valid_vendor_ref", "vendor_id IS NOT NULL")
@dlt.expect_or_drop("positive_total_amount", "total_amount > 0")
def bronze_p2p_invoices():
    return autoload_csv("p2p_invoices")


@dlt.table(name="bronze_p2p_payments", comment="Vendor payments — Auto Loader from /raw_csv/p2p_payments/",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_csv"})
@dlt.expect_or_drop("valid_payment_id", "payment_id IS NOT NULL")
@dlt.expect_or_drop("valid_invoice_ref", "invoice_id IS NOT NULL")
@dlt.expect("positive_payment", "payment_amount > 0")
def bronze_p2p_payments():
    return autoload_csv("p2p_payments")


@dlt.table(name="bronze_sales_orders", comment="Sales orders — Auto Loader from /raw_csv/sales_orders/",
           table_properties={"quality": "bronze", "domain": "O2C", "source": "raw_csv"})
@dlt.expect_or_drop("valid_so_id", "so_id IS NOT NULL")
@dlt.expect_or_drop("valid_customer_ref", "customer_id IS NOT NULL")
def bronze_sales_orders():
    return autoload_csv("sales_orders")


@dlt.table(name="bronze_o2c_invoices", comment="Customer invoices — Auto Loader from /raw_csv/o2c_invoices/",
           table_properties={"quality": "bronze", "domain": "O2C", "source": "raw_csv"})
@dlt.expect_or_drop("valid_o2c_invoice_id", "o2c_invoice_id IS NOT NULL")
@dlt.expect_or_drop("valid_customer_ref", "customer_id IS NOT NULL")
def bronze_o2c_invoices():
    return autoload_csv("o2c_invoices")


@dlt.table(name="bronze_journal_entries", comment="Journal entries — Auto Loader from /raw_csv/journal_entries/",
           table_properties={"quality": "bronze", "domain": "R2R", "source": "raw_csv"})
@dlt.expect_or_drop("valid_je_id", "je_id IS NOT NULL")
@dlt.expect("balanced_entry", "total_debit = total_credit")
def bronze_journal_entries():
    return autoload_csv("journal_entries")


@dlt.table(name="bronze_po_line", comment="PO lines — Auto Loader from /raw_csv/po_line/",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_csv"})
@dlt.expect_or_drop("valid_po_ref", "po_id IS NOT NULL")
def bronze_po_line():
    return autoload_csv("po_line")


@dlt.table(name="bronze_so_lines", comment="Sales order lines — Auto Loader from /raw_csv/so_lines/",
           table_properties={"quality": "bronze", "domain": "O2C", "source": "raw_csv"})
@dlt.expect_or_drop("valid_so_ref", "so_id IS NOT NULL")
def bronze_so_lines():
    return autoload_csv("so_lines")


@dlt.table(name="bronze_o2c_payments", comment="Customer receipts — Auto Loader from /raw_csv/o2c_payments/",
           table_properties={"quality": "bronze", "domain": "O2C", "source": "raw_csv"})
@dlt.expect_or_drop("valid_receipt_id", "receipt_id IS NOT NULL")
@dlt.expect("positive_receipt", "payment_amount > 0")
def bronze_o2c_payments():
    return autoload_csv("o2c_payments")


@dlt.table(name="bronze_je_lines", comment="Journal lines — Auto Loader from /raw_csv/je_lines/",
           table_properties={"quality": "bronze", "domain": "R2R", "source": "raw_csv"})
@dlt.expect_or_drop("valid_je_ref", "je_id IS NOT NULL")
@dlt.expect("one_sided_line", "(debit_amount = 0) != (credit_amount = 0)")
def bronze_je_lines():
    return autoload_csv("je_lines").withColumn("account_code", F.col("account_code").cast("string"))


@dlt.table(name="bronze_chart_of_accounts", comment="Chart of accounts — Auto Loader from /raw_csv/chart_of_accounts/",
           table_properties={"quality": "bronze", "domain": "R2R", "source": "raw_csv"})
def bronze_chart_of_accounts():
    return autoload_csv("chart_of_accounts").withColumn("account_code", F.col("account_code").cast("string"))


@dlt.table(name="bronze_cost_centers", comment="Cost centers — Auto Loader from /raw_csv/cost_centers/",
           table_properties={"quality": "bronze", "domain": "R2R", "source": "raw_csv"})
def bronze_cost_centers():
    return autoload_csv("cost_centers")


@dlt.table(name="bronze_recon_seed_items",
           comment="Documented reconciling items: sub-ledger documents whose GL journal is not yet posted. Seeded by the generator so the recon delta is non-zero and fully explained.",
           table_properties={"quality": "bronze", "domain": "R2R", "source": "raw_csv"})
def bronze_recon_seed_items():
    return autoload_csv("recon_seed_items").withColumn("account_code", F.col("account_code").cast("string"))


@dlt.table(name="bronze_raw_invoice_documents",
           comment="PDF invoice documents — binary Auto Loader from /raw_invoices/. "
                   "silver_invoice_extractions applies ai_parse_document + ai_extract to each file.",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_invoices_pdf"})
def bronze_raw_invoice_documents():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "binaryFile")
        .option("pathGlobFilter", "*.pdf")
        .load(f"/Volumes/{CATALOG}/{SCHEMA}/raw_invoices/")
        .select(
            F.regexp_extract(F.col("path"), r"/(INV\d+)\.pdf$", 1).alias("invoice_id"),
            F.col("path").alias("file_path"),
            F.lit("pdf").alias("file_type"),
            F.col("length").alias("file_size_bytes"),
            F.col("modificationTime").alias("file_modified_at"),
            F.col("content"),
            F.lit("PENDING").alias("processing_status"),
            F.current_timestamp().alias("_ingested_at"),
            F.lit("uc_volume").alias("_source_system"),
        )
    )


# COMMAND ----------

# MAGIC %md ## SILVER LAYER — Enrichment, deduplication, 3-way match

# COMMAND ----------

@dlt.table(name="silver_po_header", comment="Validated POs with overdue flag",
           table_properties={"quality": "silver", "domain": "P2P"})
def silver_po_header():
    return (
        dlt.read("bronze_po_header")
        .withColumn("po_date", F.to_date("po_date"))
        .withColumn("delivery_date", F.to_date("delivery_date"))
        .withColumn("approved_date",
                    F.when(F.col("approved_date") != "", F.to_date("approved_date"))
                     .otherwise(F.lit(None).cast("date")))
        .withColumn("is_overdue",
                    F.when(
                        F.col("status").isin(["APPROVED", "PARTIALLY_RECEIVED"]) &
                        (F.col("delivery_date") < F.current_date()),
                        True
                    ).otherwise(False))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["po_id"])
    )


@dlt.table(name="silver_grn", comment="Validated GRNs",
           table_properties={"quality": "silver", "domain": "P2P"})
def silver_grn():
    return (
        dlt.read("bronze_grn")
        .withColumn("grn_date", F.to_date("grn_date"))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["grn_id"])
    )


# AI extraction inside the pipeline: each PDF is parsed and extracted exactly once (streaming table).
EXTRACTION_FIELDS = [
    "invoice_number", "vendor_name", "vendor_gstin", "invoice_date", "due_date", "po_reference",
    "subtotal_amount", "cgst_amount", "sgst_amount", "total_amount", "invoice_total", "grand_total",
    "amount_payable", "currency", "bank_account_number", "ifsc_code",
]


GSTIN_PATTERN = r"([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z])"


def _amount(field):
    return F.regexp_replace(F.col(f"fields.{field}"), "[^0-9.]", "").cast("double")


@dlt.table(name="silver_invoice_extractions",
           comment="Structured fields extracted from each invoice PDF with ai_parse_document + ai_extract. Bank details and GSTIN are column-masked for users outside finance_controllers.",
           table_properties={"quality": "silver", "domain": "P2P"},
           schema=f"""
               invoice_id STRING, file_path STRING, file_size_bytes BIGINT,
               extracted_invoice_number STRING, extracted_vendor_name STRING,
               extracted_gstin STRING{MASK_GSTIN},
               extracted_invoice_date DATE, extracted_due_date DATE, extracted_po_reference STRING,
               extracted_subtotal DOUBLE, extracted_cgst DOUBLE, extracted_sgst DOUBLE,
               extracted_total_amount DOUBLE, extracted_currency STRING,
               extracted_bank_account STRING{MASK_BANK}, extracted_ifsc STRING{MASK_BANK},
               parsed_document_text STRING, extraction_method STRING, processing_status STRING,
               _processed_at TIMESTAMP, _ingested_at TIMESTAMP
           """)
def silver_invoice_extractions():
    fields_sql = "ARRAY(" + ", ".join(f"'{f}'" for f in EXTRACTION_FIELDS) + ")"
    parsed = (
        dlt.read_stream("bronze_raw_invoice_documents")
        .filter(F.col("invoice_id") != "")
        .withColumn("document_text", F.expr(
            "array_join(transform(from_json(to_json(ai_parse_document(content):document:elements), "
            "'array<struct<content:string>>'), el -> el.content), '\\n')"))
        .withColumn("fields", F.expr(f"ai_extract(document_text, {fields_sql})"))
    )
    return parsed.select(
        "invoice_id", "file_path", "file_size_bytes",
        F.col("fields.invoice_number").alias("extracted_invoice_number"),
        F.col("fields.vendor_name").alias("extracted_vendor_name"),
        # Guardrail: GSTIN has a fixed 15-character format. Keep the AI value only when it is a valid GSTIN
        # (the model otherwise invents one for foreign vendors whose PDFs print none); fall back to the
        # pattern in the parsed text.
        F.coalesce(F.when(F.upper(F.regexp_replace(F.col("fields.vendor_gstin"), r"[^A-Za-z0-9]", "")).rlike("^" + GSTIN_PATTERN + "$"),
                          F.upper(F.regexp_replace(F.col("fields.vendor_gstin"), r"[^A-Za-z0-9]", ""))),
                   F.when(F.regexp_extract("document_text", GSTIN_PATTERN, 1) != "",
                          F.regexp_extract("document_text", GSTIN_PATTERN, 1))).alias("extracted_gstin"),
        F.to_date(F.col("fields.invoice_date"), "dd-MMM-yyyy").alias("extracted_invoice_date"),
        F.to_date(F.col("fields.due_date"), "dd-MMM-yyyy").alias("extracted_due_date"),
        F.col("fields.po_reference").alias("extracted_po_reference"),
        _amount("subtotal_amount").alias("extracted_subtotal"),
        _amount("cgst_amount").alias("extracted_cgst"),
        _amount("sgst_amount").alias("extracted_sgst"),
        # Templates label the grand total differently; take the first total-style field present,
        # falling back to subtotal + CGST + SGST.
        F.coalesce(_amount("total_amount"), _amount("invoice_total"), _amount("grand_total"),
                   _amount("amount_payable"),
                   _amount("subtotal_amount") + F.coalesce(_amount("cgst_amount"), F.lit(0.0))
                   + F.coalesce(_amount("sgst_amount"), F.lit(0.0))).alias("extracted_total_amount"),
        F.col("fields.currency").alias("extracted_currency"),
        F.col("fields.bank_account_number").alias("extracted_bank_account"),
        F.col("fields.ifsc_code").alias("extracted_ifsc"),
        F.col("document_text").alias("parsed_document_text"),
        F.lit("ai_parse_document + ai_extract").alias("extraction_method"),
        F.lit("COMPLETED").alias("processing_status"),
        F.current_timestamp().alias("_processed_at"),
        F.col("_ingested_at"),
    )


def _ranked_invoices():
    """Re-submitted duplicates share vendor_id + invoice_number; the earliest document id is the original."""
    w = Window.partitionBy("vendor_id", "invoice_number").orderBy("invoice_id")
    return dlt.read("bronze_p2p_invoices").withColumn("_dup_rank", F.row_number().over(w))


@dlt.table(name="silver_duplicate_invoices",
           comment="Quarantine: re-submitted vendor invoices (same vendor and invoice number as an earlier document). Never paid, never posted to the GL.",
           table_properties={"quality": "quarantine", "domain": "P2P"})
def silver_duplicate_invoices():
    orig = (_ranked_invoices().filter(F.col("_dup_rank") == 1)
            .select("vendor_id", "invoice_number", F.col("invoice_id").alias("original_invoice_id")))
    return (
        _ranked_invoices().filter(F.col("_dup_rank") > 1)
        .join(orig, ["vendor_id", "invoice_number"], "left")
        .withColumn("invoice_date", F.to_date("invoice_date"))
        .withColumn("due_date", F.to_date("due_date"))
        .drop("_dup_rank", "_rescued_data")
        .withColumn("_quarantined_at", F.current_timestamp())
    )


@dlt.table(name="silver_p2p_invoices",
           comment="Deduplicated P2P invoices with 3-way match status and AI extraction controls. Business expectations are warn-only so the Data Quality tab shows live failed_records per rule. release_blocked is true when the PDF disagrees with the ERP on total, GSTIN or PO reference.",
           table_properties={"quality": "silver", "domain": "P2P"})
@dlt.expect("has_po_reference",          EXPECT_HAS_PO_REFERENCE)
@dlt.expect("amount_matches_po",         EXPECT_AMOUNT_MATCHES_PO)
@dlt.expect("has_grn",                   EXPECT_HAS_GRN)
@dlt.expect("has_vendor_gstin",          EXPECT_HAS_VENDOR_GSTIN)
@dlt.expect("not_critically_overdue",    EXPECT_NOT_CRITICALLY_OVERDUE)
@dlt.expect("extraction_matches_erp",    EXPECT_EXTRACTION_MATCHES_ERP)
@dlt.expect("extracted_gstin_matches",   EXPECT_EXTRACTED_GSTIN_MATCHES)
@dlt.expect("extracted_po_matches",      EXPECT_EXTRACTED_PO_MATCHES)
def silver_p2p_invoices():
    po_headers = dlt.read("silver_po_header")
    grns = dlt.read("silver_grn")
    vendors = dlt.read("bronze_vendors").select("vendor_id", F.col("country").alias("vendor_country")).dropDuplicates(["vendor_id"])
    extractions = dlt.read("silver_invoice_extractions").select(
        "invoice_id",
        F.col("extracted_total_amount").alias("ai_extracted_amount"),
        F.col("extracted_gstin").alias("ai_extracted_gstin"),
        F.col("extracted_po_reference").alias("ai_extracted_po"),
        F.col("extracted_vendor_name").alias("ai_extracted_vendor_name"),
        F.col("file_path").alias("pdf_file_path"),
    )

    deduped = _ranked_invoices().filter(F.col("_dup_rank") == 1).drop("_dup_rank")

    with_po = deduped.join(
        po_headers.select("po_id", F.col("total_amount").alias("po_total_amount"), F.col("status").alias("po_status")),
        on="po_id", how="left")
    grn_summary = grns.groupBy("po_id").agg(
        F.count("grn_id").alias("grn_count"),
        F.max("received_amount").alias("grn_received_amount"))

    checks = [
        (EXPECT_EXTRACTION_MATCHES_ERP, "PDF total differs from ERP total"),
        (EXPECT_EXTRACTED_GSTIN_MATCHES, "PDF GSTIN differs from ERP GSTIN"),
        (EXPECT_EXTRACTED_PO_MATCHES, "PDF PO reference differs from ERP PO"),
    ]
    return (
        with_po.join(grn_summary, on="po_id", how="left")
        .join(vendors, on="vendor_id", how="left")
        .join(extractions, on="invoice_id", how="left")
        .withColumn("erp_gstin_norm", _norm_id("gstin_vendor"))
        .withColumn("ai_gstin_norm", _norm_id("ai_extracted_gstin"))
        .withColumn("erp_po_norm", _norm_id("po_id"))
        .withColumn("ai_po_norm", _norm_id("ai_extracted_po"))
        .withColumn("invoice_date", F.to_date("invoice_date"))
        .withColumn("due_date", F.to_date("due_date"))
        .withColumn("has_po_ref", (F.col("po_id").isNotNull()) & (F.col("po_id") != ""))
        .withColumn("has_grn", F.coalesce(F.col("grn_count"), F.lit(0)) > 0)
        .withColumn("amount_matches_po",
                    F.abs(F.col("invoice_amount") - F.coalesce(F.col("po_total_amount"), F.lit(0.0))) <
                    F.col("invoice_amount") * 0.05)
        .withColumn("match_status",
                    F.when(F.col("has_po_ref") & F.col("has_grn") & F.col("amount_matches_po"), "THREE_WAY_MATCHED")
                     .when(F.col("has_po_ref") & F.col("amount_matches_po"), "TWO_WAY_MATCHED")
                     .when(F.col("has_po_ref") & ~F.col("amount_matches_po"), "AMOUNT_MISMATCH")
                     .when(~F.col("has_po_ref"), "NO_PO_REFERENCE")
                     .otherwise("PENDING_REVIEW"))
        .withColumn("block_reason", F.concat_ws("; ", *[F.when(~F.expr(rule), F.lit(msg)) for rule, msg in checks]))
        .withColumn("block_reason", F.when(F.col("block_reason") != "", F.col("block_reason")))
        .withColumn("release_blocked", F.col("block_reason").isNotNull())
        .withColumn("days_outstanding",
                    F.when(F.col("status") != "PAID",
                           F.datediff(F.current_date(), F.col("invoice_date"))))
        .withColumn("is_overdue", F.col("due_date") < F.current_date())
        .withColumn("_silver_processed_at", F.current_timestamp())
    )


# COMMAND ----------

# MAGIC %md ## EXCEPTIONS — every UI exception type lives in the pipeline

# COMMAND ----------

@dlt.table(name="silver_invoice_exceptions",
           comment="Every invoice an accountant would touch: re-submitted duplicates plus anything that is not a clean, unblocked THREE_WAY_MATCH. exception_type is derived from the SAME predicate constants used by the @dlt.expect decorators, so the Data Quality tab and this table stay in lockstep.",
           table_properties={"quality": "quarantine", "domain": "P2P"})
def silver_invoice_exceptions():
    enriched = (
        dlt.read("silver_p2p_invoices")
           .withColumn("days_overdue", F.datediff(F.current_date(), F.col("due_date")))
    )
    # Single source of truth: each exception_type maps to the NEGATION of one predicate constant.
    # Order matters: highest severity first. A tampered PDF outranks every matching problem.
    classified = (
        enriched
        .withColumn("exception_type",
                    F.when(F.col("release_blocked"),               "EXTRACTION_MISMATCH")
                     .when(~F.expr(EXPECT_HAS_PO_REFERENCE),       "NO_PO_REFERENCE")
                     .when(~F.expr(EXPECT_AMOUNT_MATCHES_PO),      "AMOUNT_MISMATCH")
                     .when(~F.expr(EXPECT_HAS_GRN),                "MISSING_GRN")
                     .when(~F.expr(EXPECT_HAS_VENDOR_GSTIN),       "MISSING_GSTIN")
                     .when(~F.expr(EXPECT_NOT_CRITICALLY_OVERDUE), "CRITICAL_OVERDUE")
                     .when(F.col("match_status") != "THREE_WAY_MATCHED", "PENDING_REVIEW")
                     .otherwise(None))
        .filter(F.col("exception_type").isNotNull())
    )
    duplicates = (
        dlt.read("silver_duplicate_invoices")
        .withColumn("exception_type", F.lit("DUPLICATE"))
        .withColumn("match_status", F.lit("DUPLICATE"))
        .withColumn("release_blocked", F.lit(True))
        .withColumn("block_reason", F.concat(F.lit("Duplicate of "), F.col("original_invoice_id")))
        .withColumn("days_overdue", F.datediff(F.current_date(), F.col("due_date")))
    )
    return (
        classified.unionByName(duplicates, allowMissingColumns=True)
        .withColumn("_exception_ts", F.current_timestamp())
    )


# COMMAND ----------

# MAGIC %md ## SILVER — O2C / R2R

# COMMAND ----------

@dlt.table(name="silver_o2c_invoices", comment="Validated customer invoices with aging",
           table_properties={"quality": "silver", "domain": "O2C"})
def silver_o2c_invoices():
    return (
        dlt.read("bronze_o2c_invoices")
        .withColumn("invoice_date", F.to_date("invoice_date"))
        .withColumn("due_date", F.to_date("due_date"))
        .withColumn("days_outstanding",
                    F.when(~F.col("status").isin("PAID", "WRITTEN_OFF"),
                           F.datediff(F.current_date(), F.col("invoice_date"))))
        .withColumn("days_overdue",
                    F.when(
                        ~F.col("status").isin("PAID", "WRITTEN_OFF") & (F.col("due_date") < F.current_date()),
                        F.datediff(F.current_date(), F.col("due_date"))
                    ).otherwise(F.lit(0)))
        .withColumn("aging_bucket",
                    F.when(F.col("days_outstanding") <= 30, "0-30 days")
                     .when(F.col("days_outstanding") <= 60, "31-60 days")
                     .when(F.col("days_outstanding") <= 90, "61-90 days")
                     .otherwise("90+ days"))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["o2c_invoice_id"])
    )


@dlt.table(name="silver_sales_orders", comment="Sales orders with delivery delay",
           table_properties={"quality": "silver", "domain": "O2C"})
def silver_sales_orders():
    return (
        dlt.read("bronze_sales_orders")
        .withColumn("so_date", F.to_date("so_date"))
        .withColumn("expected_delivery_date", F.to_date("expected_delivery_date"))
        .withColumn("actual_delivery_date",
                    F.when(F.col("actual_delivery_date").isNotNull() & (F.col("actual_delivery_date") != ""),
                           F.to_date("actual_delivery_date"))
                     .otherwise(F.lit(None).cast("date")))
        .withColumn("delivery_delay_days",
                    F.when(
                        F.col("actual_delivery_date").isNotNull(),
                        F.datediff(F.col("actual_delivery_date"), F.col("expected_delivery_date"))
                    ))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["so_id"])
    )


# silver_journal_entries folded into gold_fact_gl (filter posted+balanced inline)


# COMMAND ----------

# MAGIC %md ## GOLD LAYER — Business-ready facts and dims (all in this pipeline)

# COMMAND ----------

# ── P2P GOLD ─────────────────────────────────────────────────────────────────

@dlt.table(name="gold_dim_vendor",
           comment="Enriched vendor dim — folds the old silver_vendors normalization inline (dedup vendor_id, uppercase-normalize vendor_name, is_gst_registered) so the graph stays compact.",
           table_properties={"quality": "gold", "domain": "P2P"})
def gold_dim_vendor():
    # Folded silver_vendors transforms: dedup + normalize + is_gst_registered
    vendors = (
        dlt.read("bronze_vendors")
        .withColumn("vendor_name_normalized",
                    F.trim(F.regexp_replace(F.upper(F.col("vendor_name")), r"\s+", " ")))
        .withColumn("is_gst_registered",
                    F.when(F.col("gstin").isNotNull() & (F.col("gstin") != ""), True).otherwise(False))
        .dropDuplicates(["vendor_id"])
    )
    invoices = dlt.read("silver_p2p_invoices")
    payments = dlt.read("bronze_p2p_payments")

    vendor_spend = (
        invoices.filter(F.col("status") != "REJECTED")
        .groupBy("vendor_id")
        .agg(
            F.count("invoice_id").alias("total_invoices"),
            F.sum("total_amount").alias("total_spend"),
            F.avg("total_amount").alias("avg_invoice_amount"),
            F.countDistinct("po_id").alias("total_pos"),
            F.sum(F.when(F.col("match_status") == "THREE_WAY_MATCHED", 1).otherwise(0)).alias("three_way_matched_count"),
            F.sum(F.when(F.col("match_status") == "AMOUNT_MISMATCH", 1).otherwise(0)).alias("amount_mismatch_count"),
            F.sum(F.when(F.col("status") == "PENDING", 1).otherwise(0)).alias("pending_invoices"),
            F.max("invoice_date").alias("last_invoice_date"),
        )
    )
    payment_perf = (
        payments.filter(F.col("status") == "COMPLETED")
        .groupBy("vendor_id")
        .agg(
            F.count("payment_id").alias("total_payments"),
            F.sum("payment_amount").alias("total_paid_amount"),
        )
    )
    return (
        vendors.join(vendor_spend, "vendor_id", "left")
               .join(payment_perf, "vendor_id", "left")
               .select(
                   "vendor_id", "vendor_name", "vendor_name_normalized", "vendor_category",
                   "country", "city", "state", "payment_terms", "currency",
                   "gstin", "is_gst_registered", "is_active",
                   F.coalesce(F.col("total_invoices"), F.lit(0)).alias("total_invoices"),
                   F.coalesce(F.col("total_spend"), F.lit(0.0)).alias("total_spend_inr"),
                   F.coalesce(F.col("avg_invoice_amount"), F.lit(0.0)).alias("avg_invoice_amount_inr"),
                   F.coalesce(F.col("total_pos"), F.lit(0)).alias("total_purchase_orders"),
                   F.coalesce(F.col("three_way_matched_count"), F.lit(0)).alias("three_way_matched_invoices"),
                   F.coalesce(F.col("amount_mismatch_count"), F.lit(0)).alias("amount_mismatch_invoices"),
                   F.coalesce(F.col("pending_invoices"), F.lit(0)).alias("pending_invoices"),
                   F.coalesce(F.col("total_payments"), F.lit(0)).alias("total_payments_count"),
                   F.coalesce(F.col("total_paid_amount"), F.lit(0.0)).alias("total_paid_amount_inr"),
                   "last_invoice_date",
                   F.when(F.col("total_invoices") > 0,
                          F.round(F.coalesce(F.col("three_way_matched_count"), F.lit(0)) /
                                  F.col("total_invoices") * 100, 1)).alias("match_compliance_pct"),
                   F.current_timestamp().alias("_gold_processed_at"),
               )
    )


@dlt.table(name="gold_fact_invoices",
           comment="Invoice facts with aging, match status, payment timing, and PDF traceability",
           partition_cols=["invoice_year", "invoice_month"],
           table_properties={"quality": "gold", "domain": "P2P"},
           row_filter=ROW_FILTER)
def gold_fact_invoices():
    invoices = dlt.read("silver_p2p_invoices")
    po = dlt.read("silver_po_header")
    grns = dlt.read("silver_grn")
    dim_vendor = dlt.read("gold_dim_vendor")
    payments = dlt.read("bronze_p2p_payments")
    # pdf_file_path now flows in via silver_p2p_invoices (joined with silver_invoice_extractions
    # there so the @dlt.expect predicates have access to ai_extracted_amount). We just
    # normalise it here (strip the dbfs: prefix if present).

    # Only completed payments settle the liability (failed and pending ones leave it open)
    payment_info = (
        payments.filter(F.col("status") == "COMPLETED").groupBy("invoice_id").agg(
            F.min("payment_date").alias("payment_date"),
            F.sum("payment_amount").alias("paid_amount"),
            F.first("payment_method").alias("payment_method"),
        )
    )
    grn_info = (
        grns.groupBy("po_id").agg(
            F.max("grn_id").alias("grn_id"),
            F.max("grn_date").alias("grn_date"),
            F.max("received_amount").alias("grn_received_amount"),
            F.max("quality_check_status").alias("quality_check_status"),
        )
    )

    return (
        invoices
        .join(payment_info, "invoice_id", "left")
        .join(grn_info, "po_id", "left")
        .join(dim_vendor.select("vendor_id", "vendor_name", "vendor_category", "vendor_name_normalized"),
              "vendor_id", "left")
        .join(po.select("po_id", F.col("po_number"),
                        F.col("po_date").alias("po_date_from_po")),
              "po_id", "left")
        .withColumn("pdf_file_path", F.regexp_replace(F.col("pdf_file_path"), "^dbfs:", ""))
        .withColumn("payment_date", F.to_date("payment_date"))
        .withColumn("days_to_pay",
                    F.when(F.col("payment_date").isNotNull(),
                           F.datediff(F.col("payment_date"), F.col("invoice_date"))))
        .withColumn("aging_days",
                    F.when(F.col("status") != "PAID",
                           F.datediff(F.current_date(), F.col("invoice_date")))
                     .otherwise(F.col("days_to_pay")))
        .withColumn("aging_bucket",
                    F.when(F.col("aging_days") <= 30, "0-30 days")
                     .when(F.col("aging_days") <= 60, "31-60 days")
                     .when(F.col("aging_days") <= 90, "61-90 days")
                     .otherwise("90+ days"))
        .withColumn("payment_on_time",
                    F.when(F.col("payment_date").isNotNull(),
                           F.col("payment_date") <= F.col("due_date")))
        .withColumn("invoice_year",  F.year("invoice_date"))
        .withColumn("invoice_month", F.month("invoice_date"))
        .withColumn("invoice_quarter",
                    F.concat(F.year("invoice_date").cast("string"), F.lit("-Q"),
                             F.ceil(F.month(F.col("invoice_date")) / 3).cast("string")))
        .select(
            "invoice_id", "invoice_number", "po_id", "grn_id", "vendor_id",
            "vendor_name", "vendor_category", "vendor_name_normalized",
            "invoice_date", "due_date", "payment_date",
            F.col("po_date_from_po").alias("po_date"), "grn_date",
            "invoice_amount", "tax_amount",
            F.col("total_amount").alias("invoice_total_inr"),
            F.coalesce(F.col("paid_amount"), F.lit(0.0)).alias("paid_amount_inr"),
            F.col("status").alias("invoice_status"),
            "po_status", "match_status", "has_po_ref", "has_grn", "is_overdue",
            F.col("quality_check_status").alias("grn_quality_status"),
            "aging_days", "aging_bucket", "days_to_pay", "payment_on_time",
            "days_outstanding", "payment_method",
            "invoice_year", "invoice_month", "invoice_quarter",
            "gstin_vendor", "tds_applicable", "tds_rate", "legal_entity",
            "pdf_file_path", "ai_extracted_amount", "ai_extracted_gstin", "ai_extracted_po",
            "release_blocked", "block_reason",
            # Touchless = clean three-way match that the AI control did not block
            ((F.col("match_status") == "THREE_WAY_MATCHED") & ~F.col("release_blocked")).alias("is_touchless"),
            F.when(F.col("pdf_file_path").isNotNull(), F.lit("ERP_AND_PDF"))
             .otherwise(F.lit("ERP_ONLY")).alias("data_source"),
            F.current_timestamp().alias("_gold_processed_at"),
        )
    )


@dlt.table(name="gold_fact_payments",
           comment="Payment facts with timing (early/on-time/late)",
           partition_cols=["payment_year", "payment_month"],
           table_properties={"quality": "gold", "domain": "P2P"})
def gold_fact_payments():
    payments = dlt.read("bronze_p2p_payments")
    invoices = dlt.read("silver_p2p_invoices")
    dim_vendor = dlt.read("gold_dim_vendor")

    inv_for_pay = invoices.select(
        "invoice_id", "invoice_date", "due_date", "total_amount",
        F.col("vendor_id").alias("inv_vendor_id"), "po_id", "match_status",
    )
    return (
        payments
        .join(inv_for_pay, "invoice_id", "left")
        .join(dim_vendor.select(F.col("vendor_id").alias("dv_vendor_id"),
                                 "vendor_name", "vendor_category"),
              F.col("inv_vendor_id") == F.col("dv_vendor_id"), "left")
        .withColumn("payment_date", F.to_date("payment_date"))
        .withColumn("invoice_date", F.to_date("invoice_date"))
        .withColumn("due_date", F.to_date("due_date"))
        .withColumn("days_to_pay", F.datediff(F.col("payment_date"), F.col("invoice_date")))
        .withColumn("early_late_days", F.datediff(F.col("due_date"), F.col("payment_date")))
        .withColumn("payment_timing",
                    F.when(F.col("early_late_days") > 0, "EARLY")
                     .when(F.col("early_late_days") == 0, "ON_TIME")
                     .otherwise("LATE"))
        .withColumn("payment_year",  F.year("payment_date"))
        .withColumn("payment_month", F.month("payment_date"))
        .withColumn("payment_quarter",
                    F.concat(F.year("payment_date").cast("string"), F.lit("-Q"),
                             F.ceil(F.month(F.col("payment_date")) / 3).cast("string")))
        .select(
            "payment_id", "invoice_id", F.col("inv_vendor_id").alias("vendor_id"), "po_id",
            "vendor_name", "vendor_category",
            "payment_date", "invoice_date", "due_date",
            F.col("payment_amount").alias("payment_amount_inr"),
            F.col("total_amount").alias("invoice_total_inr"),
            "currency", "payment_method", "reference_number",
            F.col("status").alias("payment_status"),
            "match_status",
            "days_to_pay", "early_late_days", "payment_timing",
            "payment_year", "payment_month", "payment_quarter",
            F.current_timestamp().alias("_gold_processed_at"),
        )
    )


# ── O2C GOLD ─────────────────────────────────────────────────────────────────

@dlt.table(name="gold_dim_customer",
           comment="Enriched customer dim — folds the old silver_customers normalization inline (dedup customer_id, normalize name, is_gst_registered).",
           table_properties={"quality": "gold", "domain": "O2C"})
def gold_dim_customer():
    # Folded silver_customers transforms: dedup + normalize + is_gst_registered
    customers = (
        dlt.read("bronze_customers")
        .withColumn("customer_name_normalized",
                    F.trim(F.regexp_replace(F.upper(F.col("customer_name")), r"\s+", " ")))
        .withColumn("is_gst_registered",
                    F.when(F.col("gstin").isNotNull() & (F.col("gstin") != ""), True).otherwise(False))
        .dropDuplicates(["customer_id"])
    )
    sales_orders = dlt.read("silver_sales_orders")
    invoices = dlt.read("silver_o2c_invoices")
    pay = dlt.read("bronze_o2c_payments")

    collection_metrics = (
        invoices.join(
            pay.groupBy("o2c_invoice_id").agg(F.min("payment_date").alias("first_payment_date")),
            "o2c_invoice_id", "left",
        )
        .withColumn("first_payment_date", F.to_date("first_payment_date"))
        .withColumn("days_to_collect",
                    F.when(F.col("first_payment_date").isNotNull(),
                           F.datediff(F.col("first_payment_date"), F.col("invoice_date"))))
        .groupBy("customer_id")
        .agg(
            F.count("o2c_invoice_id").alias("total_invoices"),
            F.sum("total_amount").alias("total_billed"),
            F.sum(F.when(F.col("status") == "PAID", F.col("total_amount")).otherwise(0)).alias("total_collected"),
            F.sum(F.when(F.col("status").isin(["OUTSTANDING", "OVERDUE"]), F.col("total_amount")).otherwise(0)).alias("outstanding_ar"),
            F.avg("days_to_collect").alias("avg_days_to_collect"),
            F.sum(F.when(F.col("status") == "OVERDUE", 1).otherwise(0)).alias("overdue_invoice_count"),
            F.max("invoice_date").alias("last_invoice_date"),
        )
        .withColumn("dso",
                    F.when(F.col("total_billed") > 0,
                           F.round(F.col("outstanding_ar") / F.col("total_billed") * 90, 1)))
        .withColumn("collection_rate",
                    F.when(F.col("total_billed") > 0,
                           F.round(F.col("total_collected") / F.col("total_billed") * 100, 1)))
    )
    so_metrics = (
        sales_orders.groupBy("customer_id").agg(
            F.count("so_id").alias("total_orders"),
            F.sum("total_amount").alias("total_order_value"),
            F.avg("total_amount").alias("avg_order_value"),
        )
    )
    return (
        customers.join(collection_metrics, "customer_id", "left")
                 .join(so_metrics, "customer_id", "left")
                 .select(
                     "customer_id", "customer_name", "customer_name_normalized",
                     "segment", "industry", "country", "city", "state",
                     "payment_terms", "credit_limit", "currency",
                     "account_manager", "is_active", "is_gst_registered",
                     F.coalesce(F.col("total_orders"), F.lit(0)).alias("total_sales_orders"),
                     F.coalesce(F.col("total_order_value"), F.lit(0.0)).alias("total_order_value_inr"),
                     F.coalesce(F.col("avg_order_value"), F.lit(0.0)).alias("avg_order_value_inr"),
                     F.coalesce(F.col("total_invoices"), F.lit(0)).alias("total_invoices"),
                     F.coalesce(F.col("total_billed"), F.lit(0.0)).alias("total_billed_inr"),
                     F.coalesce(F.col("total_collected"), F.lit(0.0)).alias("total_collected_inr"),
                     F.coalesce(F.col("outstanding_ar"), F.lit(0.0)).alias("outstanding_ar_inr"),
                     "dso",
                     F.col("collection_rate").alias("collection_rate_pct"),
                     F.coalesce(F.col("avg_days_to_collect"), F.lit(0.0)).alias("avg_days_to_collect"),
                     F.coalesce(F.col("overdue_invoice_count"), F.lit(0)).alias("overdue_invoices"),
                     F.when(F.col("credit_limit") > 0,
                            F.round(F.coalesce(F.col("outstanding_ar"), F.lit(0.0)) /
                                    F.col("credit_limit") * 100, 1)).alias("credit_utilization_pct"),
                     "last_invoice_date",
                     F.current_timestamp().alias("_gold_processed_at"),
                 )
    )


@dlt.table(name="gold_fact_sales",
           comment="Sales order facts with product-mix breakdown",
           partition_cols=["so_year", "so_month"],
           table_properties={"quality": "gold", "domain": "O2C"})
def gold_fact_sales():
    sales_orders = dlt.read("silver_sales_orders")
    dim_customer = dlt.read("gold_dim_customer")
    so_lines = dlt.read("bronze_so_lines")

    product_mix = (
        so_lines.groupBy("so_id").agg(
            F.collect_list("category").alias("product_categories"),
            F.size(F.collect_set("product_code")).alias("unique_products"),
            F.sum(F.when(F.col("category") == "Software", F.col("total_line_amount")).otherwise(0)).alias("software_revenue"),
            F.sum(F.when(F.col("category") == "Services", F.col("total_line_amount")).otherwise(0)).alias("services_revenue"),
            F.sum(F.when(F.col("category") == "Support", F.col("total_line_amount")).otherwise(0)).alias("support_revenue"),
            F.sum(F.when(F.col("category") == "Infrastructure", F.col("total_line_amount")).otherwise(0)).alias("infra_revenue"),
            F.avg("discount_percentage").alias("avg_discount_pct"),
        )
    )
    return (
        sales_orders
        .join(dim_customer.select("customer_id", "customer_name", "segment", "industry"),
              "customer_id", "left")
        .join(product_mix, "so_id", "left")
        .withColumn("so_year",  F.year("so_date"))
        .withColumn("so_month", F.month("so_date"))
        .withColumn("so_quarter",
                    F.concat(F.year("so_date").cast("string"), F.lit("-Q"),
                             F.ceil(F.month(F.col("so_date")) / 3).cast("string")))
        .withColumn("revenue_excl_tax", F.round(F.col("total_amount") / 1.18, 2))
        .withColumn("gst_amount",       F.round(F.col("total_amount") - F.col("revenue_excl_tax"), 2))
        .select(
            "so_id", "so_number", "customer_id", "customer_name", "segment", "industry",
            "so_date", "expected_delivery_date", "actual_delivery_date",
            "status", "region", "sales_rep",
            F.col("total_amount").alias("so_total_inr"),
            "revenue_excl_tax", "gst_amount", "unique_products",
            F.coalesce(F.col("software_revenue"), F.lit(0.0)).alias("software_revenue_inr"),
            F.coalesce(F.col("services_revenue"), F.lit(0.0)).alias("services_revenue_inr"),
            F.coalesce(F.col("support_revenue"), F.lit(0.0)).alias("support_revenue_inr"),
            F.coalesce(F.col("infra_revenue"), F.lit(0.0)).alias("infrastructure_revenue_inr"),
            F.coalesce(F.col("avg_discount_pct"), F.lit(0.0)).alias("avg_discount_pct"),
            "delivery_delay_days",
            "so_year", "so_month", "so_quarter",
            F.current_timestamp().alias("_gold_processed_at"),
        )
    )


@dlt.table(name="gold_fact_collections",
           comment="Collections facts with aging buckets and balance outstanding",
           partition_cols=["collection_year", "collection_month"],
           table_properties={"quality": "gold", "domain": "O2C"},
           row_filter=ROW_FILTER)
def gold_fact_collections():
    invoices = dlt.read("silver_o2c_invoices")
    sales_orders = dlt.read("silver_sales_orders")
    dim_customer = dlt.read("gold_dim_customer")
    pay = dlt.read("bronze_o2c_payments")

    pay_agg = (
        pay.groupBy("o2c_invoice_id").agg(
            F.sum("payment_amount").alias("total_received"),
            F.min("payment_date").alias("first_payment_date"),
            F.max("payment_date").alias("last_payment_date"),
            F.count("receipt_id").alias("payment_count"),
            F.first("payment_method").alias("payment_method"),
        )
    )
    return (
        invoices.join(pay_agg, "o2c_invoice_id", "left")
        .join(dim_customer.select("customer_id", "customer_name", "segment", "industry"),
              "customer_id", "left")
        .join(sales_orders.select("so_id", "region", "sales_rep"), "so_id", "left")
        .withColumn("first_payment_date", F.to_date("first_payment_date"))
        .withColumn("days_to_collect",
                    F.when(F.col("first_payment_date").isNotNull(),
                           F.datediff(F.col("first_payment_date"), F.col("invoice_date"))))
        # Written-off invoices are cleared from the ledger by a write-off journal
        .withColumn("written_off_amount",
                    F.when(F.col("status") == "WRITTEN_OFF",
                           F.col("total_amount") - F.coalesce(F.col("total_received"), F.lit(0.0))).otherwise(F.lit(0.0)))
        .withColumn("balance_outstanding",
                    F.col("total_amount") - F.coalesce(F.col("total_received"), F.lit(0.0)) - F.col("written_off_amount"))
        .withColumn("is_fully_collected", F.col("balance_outstanding") <= 0)
        .withColumn("collection_year",  F.year("invoice_date"))
        .withColumn("collection_month", F.month("invoice_date"))
        .withColumn("collection_quarter",
                    F.concat(F.year("invoice_date").cast("string"), F.lit("-Q"),
                             F.ceil(F.month(F.col("invoice_date")) / 3).cast("string")))
        .select(
            "o2c_invoice_id", "invoice_number", "so_id", "customer_id", "customer_name",
            "segment", "industry", "region", "sales_rep",
            "invoice_date", "due_date", "first_payment_date",
            F.col("total_amount").alias("invoice_total_inr"),
            F.col("invoice_amount").alias("invoice_amount_excl_tax"),
            "tax_amount",
            F.coalesce(F.col("total_received"), F.lit(0.0)).alias("amount_collected_inr"),
            "balance_outstanding", "written_off_amount", "legal_entity",
            F.col("status").alias("invoice_status"),
            "aging_bucket", "days_outstanding", "days_overdue",
            "days_to_collect", "is_fully_collected",
            F.col("payment_count").alias("payment_installments"),
            "payment_method",
            "collection_year", "collection_month", "collection_quarter",
            F.current_timestamp().alias("_gold_processed_at"),
        )
    )


# ── R2R GOLD ─────────────────────────────────────────────────────────────────

@dlt.table(name="gold_fact_gl",
           comment="GL entries enriched with COA/cost-center metadata — folds the old silver_journal_entries inline (filter POSTED + balanced, dates as DATE, fiscal_quarter).",
           partition_cols=["gl_year", "gl_month"],
           table_properties={"quality": "gold", "domain": "R2R"})
def gold_fact_gl():
    # Folded silver_journal_entries transforms inline: only posted + balanced JEs
    silver_je = (
        dlt.read("bronze_journal_entries")
        .filter(F.abs(F.col("total_debit") - F.col("total_credit")) <= 0.005)
        .filter(F.col("status") == "POSTED")
        .withColumn("je_date", F.to_date("je_date"))
        # Derive the posting period from the date so CSV type inference cannot alter it
        .withColumn("period", F.date_format("je_date", "yyyy-MM"))
        .withColumn("fiscal_year", F.year("je_date"))
        .withColumn("fiscal_quarter",
                    F.concat(F.col("fiscal_year").cast("string"), F.lit("-Q"),
                             F.ceil(F.month(F.col("je_date")) / 3).cast("string")))
        .dropDuplicates(["je_id"])
        .select("je_id", "je_number", "je_date", "je_type", "period",
                "fiscal_year", "fiscal_quarter", "status", "posted_by",
                "source_module", "source_document_id")
    )
    je_lines = dlt.read("bronze_je_lines")
    coa = dlt.read("bronze_chart_of_accounts")
    cc = dlt.read("bronze_cost_centers")

    return (
        je_lines
        .join(silver_je, "je_id", "inner")
        .join(coa.select("account_code", "account_name", "account_type", "account_subtype"),
              "account_code", "left")
        .join(cc.select(F.col("cost_center_code").alias("cost_center"),
                         "cost_center_name", "department"),
              "cost_center", "left")
        .withColumn("je_date", F.to_date("je_date"))
        .withColumn("amount", F.col("debit_amount") - F.col("credit_amount"))
        .withColumn("gl_year",  F.year("je_date"))
        .withColumn("gl_month", F.month("je_date"))
        .withColumn("gl_quarter",
                    F.concat(F.year("je_date").cast("string"), F.lit("-Q"),
                             F.ceil(F.month(F.col("je_date")) / 3).cast("string")))
        .withColumn("normal_balance",
                    F.when(F.col("account_type").isin(["Asset", "Expense"]), "DEBIT")
                     .otherwise("CREDIT"))
        .select(
            "je_id", "je_number",
            F.col("line_number").alias("gl_line_number"),
            "account_code", "account_name", "account_type", "account_subtype",
            "cost_center", "cost_center_name", "department",
            "je_date", "period", "fiscal_year", "fiscal_quarter",
            "gl_year", "gl_month", "gl_quarter",
            "je_type", "status", "posted_by", "source_module", "source_document_id",
            F.col("debit_amount").alias("debit_inr"),
            F.col("credit_amount").alias("credit_inr"),
            F.col("amount").alias("net_amount_inr"),
            "normal_balance",
            F.col("description").alias("gl_description"),
            F.current_timestamp().alias("_gold_processed_at"),
        )
    )


@dlt.table(name="silver_je_quarantine",
           comment="Quarantine: journal headers whose debits and credits do not balance. Excluded from gold_fact_gl.",
           table_properties={"quality": "quarantine", "domain": "R2R"})
def silver_je_quarantine():
    return (
        dlt.read("bronze_journal_entries")
        .filter(F.abs(F.col("total_debit") - F.col("total_credit")) > 0.005)
        .withColumn("imbalance_inr", F.round(F.col("total_debit") - F.col("total_credit"), 2))
        .drop("_rescued_data")
        .withColumn("_quarantined_at", F.current_timestamp())
    )


@dlt.table(name="gold_fact_trial_balance",
           comment="Period-end trial balance from posted journal lines. One row per account and period (full account x period grid). closing_balance_inr is the inception-to-date balance with its natural sign in balance_type; the DR and CR closing balances are equal in every period.",
           partition_cols=["fiscal_year"],
           table_properties={"quality": "gold", "domain": "R2R"})
def gold_fact_trial_balance():
    gl = dlt.read("gold_fact_gl")
    coa = dlt.read("bronze_chart_of_accounts").select("account_code", "account_name", "account_type", "account_subtype")
    activity = (
        gl.groupBy("period", "account_code")
          .agg(F.sum("debit_inr").alias("period_debit"),
               F.sum("credit_inr").alias("period_credit"),
               F.count("je_id").alias("transaction_count"))
    )
    grid = gl.select("period").distinct().crossJoin(coa)
    ytd = Window.partitionBy("account_code", "fiscal_year").orderBy("period").rowsBetween(Window.unboundedPreceding, Window.currentRow)
    itd = Window.partitionBy("account_code").orderBy("period").rowsBetween(Window.unboundedPreceding, Window.currentRow)
    return (
        grid.join(activity, ["period", "account_code"], "left")
        .fillna(0, subset=["period_debit", "period_credit", "transaction_count"])
        .withColumn("fiscal_year", F.substring("period", 1, 4).cast("int"))
        .withColumn("fiscal_quarter", F.concat(F.col("fiscal_year").cast("string"), F.lit("-Q"),
                                               F.ceil(F.substring("period", 6, 2).cast("int") / 3).cast("string")))
        .withColumn("period_net", F.col("period_debit") - F.col("period_credit"))
        .withColumn("ytd_debit", F.sum("period_debit").over(ytd))
        .withColumn("ytd_credit", F.sum("period_credit").over(ytd))
        .withColumn("ytd_net", F.col("ytd_debit") - F.col("ytd_credit"))
        .withColumn("cumulative_debit", F.sum("period_debit").over(itd))
        .withColumn("cumulative_credit", F.sum("period_credit").over(itd))
        .withColumn("closing_net_inr", F.round(F.col("cumulative_debit") - F.col("cumulative_credit"), 2))
        .filter((F.col("cumulative_debit") + F.col("cumulative_credit")) > 0)
        .withColumn("balance_type", F.when(F.col("closing_net_inr") >= 0, "DR").otherwise("CR"))
        .withColumn("closing_balance_inr", F.abs(F.col("closing_net_inr")))
        .select("fiscal_year", "fiscal_quarter", "period",
                "account_code", "account_name", "account_type", "account_subtype",
                "period_debit", "period_credit", "period_net",
                "ytd_debit", "ytd_credit", "ytd_net",
                "closing_net_inr", "closing_balance_inr", "balance_type", "transaction_count",
                F.current_timestamp().alias("_gold_processed_at"))
    )


def _ar_open_items():
    """AR sub-ledger open items: invoice gross less receipts, written-off invoices cleared."""
    receipts = dlt.read("bronze_o2c_payments").groupBy("o2c_invoice_id").agg(F.sum("payment_amount").alias("received"))
    return (
        dlt.read("silver_o2c_invoices").join(receipts, "o2c_invoice_id", "left")
        .withColumn("open_amount",
                    F.when(F.col("status") == "WRITTEN_OFF", F.lit(0.0))
                     .otherwise(F.col("total_amount") - F.coalesce(F.col("received"), F.lit(0.0))))
    )


def _ap_open_items():
    """AP sub-ledger open items: accepted (non-rejected) invoices less completed payments."""
    paid = (dlt.read("bronze_p2p_payments").filter(F.col("status") == "COMPLETED")
            .groupBy("invoice_id").agg(F.sum("payment_amount").alias("paid")))
    return (
        dlt.read("silver_p2p_invoices").filter(F.col("status") != "REJECTED")
        .join(paid, "invoice_id", "left")
        .withColumn("open_amount", F.col("total_amount") - F.coalesce(F.col("paid"), F.lit(0.0)))
    )


@dlt.table(name="gold_recon_reconciling_items",
           comment="Each documented reconciling item between a sub-ledger and its GL control account: the document, amount, reason and the status of its GL journal.",
           table_properties={"quality": "gold", "domain": "R2R"})
def gold_recon_reconciling_items():
    je = dlt.read("bronze_journal_entries").select(F.col("je_id").alias("gl_je_id"), F.col("status").alias("current_je_status"))
    coa = dlt.read("bronze_chart_of_accounts").select("account_code", "account_name")
    return (
        dlt.read("bronze_recon_seed_items")
        .join(coa, "account_code", "left")
        .join(je, "gl_je_id", "left")
        .select("account_code", "account_name", "document_id", "document_type",
                F.col("amount").cast("double").alias("amount"), "reason", "gl_je_id",
                F.coalesce(F.col("current_je_status"), F.col("gl_je_status")).alias("gl_je_status"),
                F.current_timestamp().alias("_gold_processed_at"))
    )


@dlt.table(name="gold_recon_subledger_vs_gl",
           comment="Sub-ledger vs GL control-account reconciliation. delta = sub-ledger open balance - GL balance; unexplained_delta removes the documented reconciling items. tied is true only when the unexplained delta is below one rupee.",
           table_properties={"quality": "gold", "domain": "Cross"})
def gold_recon_subledger_vs_gl():
    gl = dlt.read("gold_fact_gl")
    cutoff = gl.agg(F.max("je_date").alias("cutoff_date"))
    gl_bal = (
        gl.filter(F.col("account_code").isin("1100", "2000"))
          .groupBy("account_code")
          .agg(F.sum("debit_inr").alias("dr"), F.sum("credit_inr").alias("cr"))
          # Natural balance: AR is a debit balance, AP a credit balance
          .withColumn("gl_amount", F.when(F.col("account_code") == "1100", F.col("dr") - F.col("cr"))
                                    .otherwise(F.col("cr") - F.col("dr")))
          .select("account_code", "gl_amount")
    )
    sub = (
        _ar_open_items().agg(F.sum("open_amount").alias("subledger_amount"))
            .withColumn("account_code", F.lit("1100"))
            .withColumn("account_name", F.lit("Accounts Receivable"))
            .withColumn("balance_type", F.lit("DR"))
            .withColumn("subledger_source", F.lit("silver_o2c_invoices less bronze_o2c_payments (gold_fact_collections.balance_outstanding)"))
        .unionByName(
        _ap_open_items().agg(F.sum("open_amount").alias("subledger_amount"))
            .withColumn("account_code", F.lit("2000"))
            .withColumn("account_name", F.lit("Accounts Payable"))
            .withColumn("balance_type", F.lit("CR"))
            .withColumn("subledger_source", F.lit("silver_p2p_invoices less completed bronze_p2p_payments (gold_fact_invoices)")))
    )
    items = (dlt.read("gold_recon_reconciling_items").filter(F.col("gl_je_status") != "POSTED")
             .groupBy("account_code")
             .agg(F.sum("amount").alias("reconciling_items_amount"), F.count("*").alias("reconciling_items_count")))
    return (
        sub.join(gl_bal, "account_code", "left").join(items, "account_code", "left").crossJoin(cutoff)
        .fillna(0, subset=["gl_amount", "reconciling_items_amount", "reconciling_items_count"])
        .withColumn("subledger_amount", F.round("subledger_amount", 2))
        .withColumn("gl_amount", F.round("gl_amount", 2))
        .withColumn("delta", F.round(F.col("subledger_amount") - F.col("gl_amount"), 2))
        .withColumn("unexplained_delta", F.round(F.col("delta") - F.col("reconciling_items_amount"), 2))
        .withColumn("tied", F.abs(F.col("unexplained_delta")) < F.lit(1.0))
        .select("account_code", "account_name", "balance_type", "subledger_source",
                "subledger_amount", "gl_amount", "delta",
                "reconciling_items_amount", "reconciling_items_count", "unexplained_delta", "tied",
                "cutoff_date", F.current_timestamp().alias("_gold_processed_at"))
    )


# COMMAND ----------

# MAGIC %md ## OPERATIONAL SERVING — source of the Lakebase synced table

# COMMAND ----------

@dlt.table(name="gold_ap_exception_queue",
           comment="Open AP work queue (every exception and release-blocked invoice). Synced to Lakebase Postgres as ops.ap_exception_queue so the app reads it at OLTP latency.",
           table_properties={"quality": "gold", "domain": "P2P", "delta.enableChangeDataFeed": "true"})
def gold_ap_exception_queue():
    vendors = dlt.read("bronze_vendors").select("vendor_id", "vendor_name").dropDuplicates(["vendor_id"])
    return (
        dlt.read("silver_invoice_exceptions")
        .join(vendors, "vendor_id", "left")
        .select("invoice_id", "invoice_number", "vendor_id", "vendor_name", "legal_entity",
                "invoice_date", "due_date",
                F.col("total_amount").cast("double").alias("invoice_total_inr"),
                "match_status", "exception_type",
                F.coalesce(F.col("release_blocked"), F.lit(False)).alias("release_blocked"),
                "block_reason", "ai_extracted_amount", "pdf_file_path",
                F.datediff(F.current_date(), F.col("invoice_date")).alias("aging_days"))
    )
