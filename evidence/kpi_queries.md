# KPI queries and results

_Collected 2026-10-29 12:32 UTC from `https://fevm-akash-fevm-ts.cloud.databricks.com`, `akash_fevm_ts_catalog.finance_ops_control_tower`._

### Touchless rate (clean three-way match, not release-blocked)

```sql
SELECT COUNT(*) AS invoices,
       SUM(CASE WHEN match_status = 'THREE_WAY_MATCHED' THEN 1 ELSE 0 END) AS three_way_matched,
       SUM(CASE WHEN release_blocked THEN 1 ELSE 0 END) AS release_blocked,
       SUM(CASE WHEN is_touchless THEN 1 ELSE 0 END) AS touchless,
       ROUND(100 * AVG(CASE WHEN is_touchless THEN 1 ELSE 0 END), 1) AS touchless_pct
FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_invoices
```

| invoices | three_way_matched | release_blocked | touchless | touchless_pct |
|---|---|---|---|---|
| 550 | 190 | 3 | 189 | 34.4 |

### Exceptions by type (open work queue)

```sql
SELECT exception_type, COUNT(*) AS invoices, ROUND(SUM(total_amount) / 1e7, 2) AS value_inr_cr
FROM akash_fevm_ts_catalog.finance_ops_control_tower.silver_invoice_exceptions GROUP BY exception_type ORDER BY invoices DESC
```

| exception_type | invoices | value_inr_cr |
|---|---|---|
| MISSING_GRN | 188 | 211.64 |
| AMOUNT_MISMATCH | 98 | 119.88 |
| NO_PO_REFERENCE | 72 | 24.31 |
| DUPLICATE | 27 | 26.77 |
| CRITICAL_OVERDUE | 16 | 20.74 |
| EXTRACTION_MISMATCH | 3 | 2.87 |
| MISSING_GSTIN | 3 | 4.03 |

### Value held for review (all open exceptions)

```sql
SELECT COUNT(*) AS invoices, ROUND(SUM(invoice_total_inr) / 1e7, 2) AS value_inr_cr,
       SUM(CASE WHEN release_blocked THEN 1 ELSE 0 END) AS release_blocked
FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_ap_exception_queue
```

| invoices | value_inr_cr | release_blocked |
|---|---|---|
| 407 | 410.24 | 30 |

### Duplicates blocked before payment

```sql
SELECT COUNT(*) AS duplicates, ROUND(SUM(total_amount) / 1e7, 2) AS value_inr_cr
FROM akash_fevm_ts_catalog.finance_ops_control_tower.silver_duplicate_invoices
```

| duplicates | value_inr_cr |
|---|---|
| 27 | 26.77 |

### Tampered PDFs caught by the AI control

```sql
SELECT t.invoice_id, t.true_total_inr, t.printed_total_inr, t.corruption_pct,
       i.release_blocked, i.block_reason, i.match_status
FROM akash_fevm_ts_catalog.finance_ops_control_tower.silver_pdf_corruption_log t LEFT JOIN akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_invoices i USING (invoice_id) ORDER BY t.invoice_id
```

| invoice_id | true_total_inr | printed_total_inr | corruption_pct | release_blocked | block_reason | match_status |
|---|---|---|---|---|---|---|
| INV000128 | 3541805.69 | 3931404.32 | 11.0 | true | PDF total differs from ERP total | NO_PO_REFERENCE |
| INV000198 | 7454589.9 | 7976411.19 | 7.0 | true | PDF total differs from ERP total | THREE_WAY_MATCHED |
| INV000204 | 1.767717762E7 | 1.697009052E7 | -4.0 | true | PDF total differs from ERP total | AMOUNT_MISMATCH |

### Invoice GSTIN matches the vendor master (Indian vendors)

```sql
SELECT ROUND(100 * AVG(CASE WHEN i.gstin_vendor = v.gstin THEN 1 ELSE 0 END), 1) AS gstin_match_pct,
       SUM(CASE WHEN i.gstin_vendor IS NULL OR i.gstin_vendor = '' THEN 1 ELSE 0 END) AS invoices_missing_gstin,
       COUNT(*) AS invoices
FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_invoices i JOIN akash_fevm_ts_catalog.finance_ops_control_tower.gold_dim_vendor v USING (vendor_id) WHERE v.country = 'India'
```

| gstin_match_pct | invoices_missing_gstin | invoices |
|---|---|---|
| 97.9 | 8 | 383 |

### Accounts receivable: open balance, customers, average days outstanding

```sql
SELECT ROUND(SUM(balance_outstanding) / 1e7, 2) AS open_ar_inr_cr,
       COUNT(DISTINCT CASE WHEN balance_outstanding > 0 THEN customer_id END) AS customers_with_open_ar,
       ROUND(AVG(CASE WHEN balance_outstanding > 0 THEN days_outstanding END), 1) AS avg_days_outstanding,
       SUM(CASE WHEN aging_bucket = '90+ days' AND balance_outstanding > 0 THEN 1 ELSE 0 END) AS invoices_90_plus
FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_collections
```

| open_ar_inr_cr | customers_with_open_ar | avg_days_outstanding | invoices_90_plus |
|---|---|---|---|
| 17.37 | 37 | 59.4 | 5 |

### Accounts payable: open balance

```sql
SELECT ROUND(SUM(invoice_total_inr - paid_amount_inr) / 1e7, 2) AS open_ap_inr_cr, COUNT(*) AS invoices
FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_invoices WHERE invoice_status != 'REJECTED'
```

| open_ap_inr_cr | invoices |
|---|---|
| 178.17 | 521 |

### Unbalanced journals quarantined

```sql
SELECT COUNT(*) AS journals, ROUND(SUM(imbalance_inr), 2) AS total_imbalance_inr FROM akash_fevm_ts_catalog.finance_ops_control_tower.silver_je_quarantine
```

| journals | total_imbalance_inr |
|---|---|
| 5 | 66352.0 |

### AI extraction evaluation (latest MLflow run)

```sql
SELECT metric, value, mlflow_run_id FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_ai_extraction_eval
WHERE mlflow_run_id = (SELECT max_by(mlflow_run_id, evaluated_at) FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_ai_extraction_eval) ORDER BY metric
```

| metric | value | mlflow_run_id |
|---|---|---|
| accuracy_due_date | 1.0 | f6233b66d98c47d99e58cb7b938421bc |
| accuracy_gstin | 1.0 | f6233b66d98c47d99e58cb7b938421bc |
| accuracy_invoice_date | 1.0 | f6233b66d98c47d99e58cb7b938421bc |
| accuracy_invoice_number | 1.0 | f6233b66d98c47d99e58cb7b938421bc |
| accuracy_po_reference | 1.0 | f6233b66d98c47d99e58cb7b938421bc |
| accuracy_total | 1.0 | f6233b66d98c47d99e58cb7b938421bc |
| clean_blocked_false_positives | 0.0 | f6233b66d98c47d99e58cb7b938421bc |
| documents_evaluated | 200.0 | f6233b66d98c47d99e58cb7b938421bc |
| false_positive_rate | 0.0 | f6233b66d98c47d99e58cb7b938421bc |
| tamper_precision | 1.0 | f6233b66d98c47d99e58cb7b938421bc |
| tamper_recall | 1.0 | f6233b66d98c47d99e58cb7b938421bc |
| tampered_caught | 3.0 | f6233b66d98c47d99e58cb7b938421bc |
| tampered_documents | 3.0 | f6233b66d98c47d99e58cb7b938421bc |

### Row counts per governed table

```sql
SELECT table_name, table_type FROM akash_fevm_ts_catalog.information_schema.tables
WHERE table_schema = 'finance_ops_control_tower' ORDER BY table_name
```

| table_name | table_type |
|---|---|
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_chart_of_accounts_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_cost_centers_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_customers_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_grn_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_je_lines_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_journal_entries_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_o2c_invoices_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_o2c_payments_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_p2p_invoices_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_p2p_payments_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_po_header_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_po_line_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_raw_invoice_documents_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_recon_seed_items_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_sales_orders_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_so_lines_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_bronze_vendors_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_gold_ap_exception_queue_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_gold_dim_customer_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_gold_dim_vendor_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_gold_fact_collections_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_gold_fact_gl_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_gold_fact_invoices_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_gold_fact_payments_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_gold_fact_sales_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_gold_fact_trial_balance_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_gold_recon_reconciling_items_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_gold_recon_subledger_vs_gl_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_silver_duplicate_invoices_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_silver_grn_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_silver_invoice_exceptions_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_silver_invoice_extractions_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_silver_je_quarantine_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_silver_o2c_invoices_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_silver_p2p_invoices_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_silver_po_header_1 | MANAGED |
| __materialization_mat_b6b62b82_aef9_48fc_b74d_c1ca9d868a92_silver_sales_orders_1 | MANAGED |
| ap_exception_queue | FOREIGN |
| bronze_chart_of_accounts | STREAMING_TABLE |
| bronze_cost_centers | STREAMING_TABLE |
| bronze_customers | STREAMING_TABLE |
| bronze_grn | STREAMING_TABLE |
| bronze_je_lines | STREAMING_TABLE |
| bronze_journal_entries | STREAMING_TABLE |
| bronze_o2c_invoices | STREAMING_TABLE |
| bronze_o2c_payments | STREAMING_TABLE |
| bronze_p2p_invoices | STREAMING_TABLE |
| bronze_p2p_payments | STREAMING_TABLE |
| bronze_po_header | STREAMING_TABLE |
| bronze_po_line | STREAMING_TABLE |

_33 more rows not shown._
