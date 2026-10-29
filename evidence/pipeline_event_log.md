# Pipeline event log — data quality

_Collected 2026-10-29 12:32 UTC from `https://fevm-akash-fevm-ts.cloud.databricks.com`, `akash_fevm_ts_catalog.finance_ops_control_tower`._

### Expectation pass/fail per rule (latest update)

```sql
WITH latest AS (SELECT origin.update_id AS u FROM event_log('b6b62b82-aef9-48fc-b74d-c1ca9d868a92') WHERE event_type = 'create_update' ORDER BY timestamp DESC LIMIT 1),
exp AS (
  SELECT origin.flow_name AS flow, explode(from_json(details:flow_progress:data_quality:expectations,
         'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) AS e
  FROM event_log('b6b62b82-aef9-48fc-b74d-c1ca9d868a92') WHERE event_type = 'flow_progress' AND origin.update_id = (SELECT u FROM latest)
    AND details:flow_progress:data_quality:expectations IS NOT NULL)
SELECT e.dataset, e.name AS expectation, SUM(e.passed_records) AS passed, SUM(e.failed_records) AS failed
FROM exp GROUP BY 1, 2 ORDER BY 1, 2
```

| dataset | expectation | passed | failed |
|---|---|---|---|
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_customers | valid_customer_id | 150 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_customers | valid_customer_name | 150 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_grn | valid_grn_id | 206 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_grn | valid_po_ref | 206 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_je_lines | one_sided_line | 4747 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_je_lines | valid_je_ref | 4747 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_journal_entries | balanced_entry | 1977 | 5 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_journal_entries | valid_je_id | 1982 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_o2c_invoices | valid_customer_ref | 262 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_o2c_invoices | valid_o2c_invoice_id | 262 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_o2c_payments | positive_receipt | 229 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_o2c_payments | valid_receipt_id | 229 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_invoices | positive_total_amount | 577 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_invoices | valid_invoice_id | 577 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_invoices | valid_vendor_ref | 577 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_payments | positive_payment | 382 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_payments | valid_invoice_ref | 382 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_p2p_payments | valid_payment_id | 382 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_po_header | positive_amount | 500 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_po_header | valid_po_id | 500 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_po_header | valid_vendor_ref | 500 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_po_line | valid_po_ref | 2191 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_sales_orders | valid_customer_ref | 600 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_sales_orders | valid_so_id | 600 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_so_lines | valid_so_ref | 1842 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_vendors | valid_email | 100 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_vendors | valid_vendor_id | 100 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.bronze_vendors | valid_vendor_name | 100 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | amount_matches_po | 451 | 99 |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | extracted_gstin_matches | 550 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | extracted_po_matches | 550 | 0 |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | extraction_matches_erp | 547 | 3 |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | has_grn | 253 | 297 |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | has_po_reference | 477 | 73 |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | has_vendor_gstin | 542 | 8 |
| akash_fevm_ts_catalog.finance_ops_control_tower.silver_p2p_invoices | not_critically_overdue | 514 | 36 |

### Pipeline updates

```sql
SELECT origin.update_id, timestamp, details:update_progress:state AS state
FROM event_log('b6b62b82-aef9-48fc-b74d-c1ca9d868a92') WHERE event_type = 'update_progress'
  AND details:update_progress:state IN ('COMPLETED', 'FAILED', 'CANCELED') ORDER BY timestamp DESC LIMIT 10
```

| update_id | timestamp | state |
|---|---|---|
| d87797b5-7447-498c-b9e8-5d3f3bb62428 | 2026-10-29T12:21:18.390Z | COMPLETED |
| b0b28a45-3338-4853-a688-6aa26adae6e4 | 2026-10-29T12:04:23.002Z | COMPLETED |
| f9c073ef-2f9c-4485-a893-4d4b56c20e19 | 2026-10-29T11:52:00.412Z | COMPLETED |
| 8ef78088-efd7-4fca-8873-6e2d5caa7608 | 2026-10-29T11:38:40.959Z | COMPLETED |
| 625d39da-50d7-46fc-9dba-b3114c8b1a80 | 2026-10-29T11:22:55.229Z | COMPLETED |
