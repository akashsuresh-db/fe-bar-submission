# Lineage — layers connected

_Collected 2026-10-29 12:32 UTC from `https://fevm-akash-fevm-ts.cloud.databricks.com`, `akash_fevm_ts_catalog.finance_ops_control_tower`._

### Table lineage within the schema (raw volumes → bronze → silver → gold → Lakebase synced table)

```sql
SELECT DISTINCT COALESCE(source_table_full_name, source_path) AS source, target_table_full_name AS target, entity_type
FROM system.access.table_lineage
WHERE (target_table_full_name LIKE 'akash_fevm_ts_catalog.finance_ops_control_tower.%' OR source_table_full_name LIKE 'akash_fevm_ts_catalog.finance_ops_control_tower.%')
  AND event_date >= current_date() - INTERVAL 2 DAYS
ORDER BY target, source
```

| source | target | entity_type |
|---|---|---|
| akash_fevm_ts_catalog.finance_ops_control_tower.ap_exception_queue |  | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_invoices |  | JOB |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_invoices |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_vendors |  | JOB |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_vendors |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.event_log_ad512c9c_14c1_4e70_82d7_ed13321b60b9 |  | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.event_log_b6b62b82_aef9_48fc_b74d_c1ca9d868a92 |  | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_ap_exception_queue |  | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_ap_exception_queue |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_collections |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_invoices |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_payments |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_trial_balance |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_reconciling_items |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_subledger_vs_gl |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_duplicate_invoices |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_invoice_exceptions |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_invoice_extractions |  | JOB |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_invoice_extractions |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_je_quarantine |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices |  | JOB |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_pdf_corruption_log |  | JOB |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_pdf_corruption_log |  |  |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_ap_exception_queue | akash_fevm_ts_catalog.finance_ops_control_tower.ap_exception_queue | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_chart_of_accounts | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_cost_centers | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_customers | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_grn | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_je_lines | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_journal_entries | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_o2c_invoices | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_o2c_payments | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_invoices | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_payments | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_po_header | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_po_line | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_raw_invoice_documents | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_recon_seed_items | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_sales_orders | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_so_lines | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.bronze_vendors | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.event_log_ad512c9c_14c1_4e70_82d7_ed13321b60b9 | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.event_log_b6b62b82_aef9_48fc_b74d_c1ca9d868a92 | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.gold_ai_extraction_eval | JOB |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_vendors | akash_fevm_ts_catalog.finance_ops_control_tower.gold_ap_exception_queue | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_invoice_exceptions | akash_fevm_ts_catalog.finance_ops_control_tower.gold_ap_exception_queue | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_customers | akash_fevm_ts_catalog.finance_ops_control_tower.gold_dim_customer | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_o2c_payments | akash_fevm_ts_catalog.finance_ops_control_tower.gold_dim_customer | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_o2c_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.gold_dim_customer | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_sales_orders | akash_fevm_ts_catalog.finance_ops_control_tower.gold_dim_customer | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_payments | akash_fevm_ts_catalog.finance_ops_control_tower.gold_dim_vendor | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_vendors | akash_fevm_ts_catalog.finance_ops_control_tower.gold_dim_vendor | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.gold_dim_vendor | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_o2c_payments | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_collections | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_dim_customer | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_collections | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_o2c_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_collections | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_sales_orders | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_collections | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_chart_of_accounts | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_gl | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_cost_centers | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_gl | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_je_lines | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_gl | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_journal_entries | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_gl | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_payments | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_invoices | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_dim_vendor | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_invoices | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_grn | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_invoices | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_invoices | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_po_header | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_invoices | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_payments | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_payments | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_dim_vendor | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_payments | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_payments | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_so_lines | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_sales | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_dim_customer | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_sales | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_sales_orders | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_sales | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_chart_of_accounts | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_trial_balance | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_gl | akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_trial_balance | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_chart_of_accounts | akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_reconciling_items | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_journal_entries | akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_reconciling_items | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_recon_seed_items | akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_reconciling_items | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_o2c_payments | akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_subledger_vs_gl | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_payments | akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_subledger_vs_gl | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_gl | akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_subledger_vs_gl | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_reconciling_items | akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_subledger_vs_gl | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_o2c_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_subledger_vs_gl | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_subledger_vs_gl | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.gov_entity_access | JOB |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.silver_duplicate_invoices | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_grn | akash_fevm_ts_catalog.finance_ops_control_tower.silver_grn | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_duplicate_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.silver_invoice_exceptions | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.silver_invoice_exceptions | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_raw_invoice_documents | akash_fevm_ts_catalog.finance_ops_control_tower.silver_invoice_extractions | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_journal_entries | akash_fevm_ts_catalog.finance_ops_control_tower.silver_je_quarantine | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_o2c_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.silver_o2c_invoices | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_vendors | akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_grn | akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_invoice_extractions | akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_po_header | akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | PIPELINE |
|  | akash_fevm_ts_catalog.finance_ops_control_tower.silver_pdf_corruption_log | JOB |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_po_header | akash_fevm_ts_catalog.finance_ops_control_tower.silver_po_header | PIPELINE |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_sales_orders | akash_fevm_ts_catalog.finance_ops_control_tower.silver_sales_orders | PIPELINE |
