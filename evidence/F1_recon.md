# F1 — Reconciliation and trial balance

_Collected 2026-10-29 12:32 UTC from `https://fevm-akash-fevm-ts.cloud.databricks.com`, `akash_fevm_ts_catalog.finance_ops_control_tower`._

### Trial balance: every period balances (expect 0 rows)

```sql
SELECT period, ROUND(SUM(CASE WHEN balance_type = 'DR' THEN closing_balance_inr ELSE -closing_balance_inr END), 2) AS net
FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_trial_balance GROUP BY period HAVING ABS(net) > 1
```

| period | net |
|---|---|

### Trial balance totals, latest period

```sql
SELECT period, ROUND(SUM(CASE WHEN balance_type = 'DR' THEN closing_balance_inr END) / 1e7, 4) AS dr_inr_cr,
       ROUND(SUM(CASE WHEN balance_type = 'CR' THEN closing_balance_inr END) / 1e7, 4) AS cr_inr_cr, COUNT(*) AS accounts
FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_trial_balance WHERE period = (SELECT MAX(period) FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_trial_balance) GROUP BY period
```

| period | dr_inr_cr | cr_inr_cr | accounts |
|---|---|---|---|
| 2026-10 | 661.3034 | 661.3034 | 25 |

### Sub-ledger vs GL reconciliation

```sql
SELECT * EXCEPT (_gold_processed_at) FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_subledger_vs_gl ORDER BY account_code
```

| account_code | account_name | balance_type | subledger_source | subledger_amount | gl_amount | delta | reconciling_items_amount | reconciling_items_count | unexplained_delta | tied | cutoff_date |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1100 | Accounts Receivable | DR | silver_o2c_invoices less bronze_o2c_payments (gold_fact_collections.balance_outstanding) | 1.7368229084E8 | 1.5836589084E8 | 1.53164E7 | 1.53164E7 | 3 | 0.0 | true | 2026-10-29 |
| 2000 | Accounts Payable | CR | silver_p2p_invoices less completed bronze_p2p_payments (gold_fact_invoices) | 1.78167890038E9 | 1.77371102454E9 | 7967875.84 | 7967875.84 | 1 | 0.0 | true | 2026-10-29 |

### Reconciling items

```sql
SELECT * EXCEPT (_gold_processed_at) FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_recon_reconciling_items ORDER BY account_code
```

| account_code | account_name | document_id | document_type | amount | reason | gl_je_id | gl_je_status |
|---|---|---|---|---|---|---|---|
| 1100 | Accounts Receivable | CINV000130 | AR_INVOICE | 851960.0 | Invoice posted in the AR sub-ledger; GL journal still in DRAFT awaiting approval | JE000132 | DRAFT |
| 1100 | Accounts Receivable | CINV000157 | AR_INVOICE | 1213335.0 | Invoice posted in the AR sub-ledger; GL journal still in DRAFT awaiting approval | JE000159 | DRAFT |
| 1100 | Accounts Receivable | CINV000242 | AR_INVOICE | 1.3251105E7 | Invoice posted in the AR sub-ledger; GL journal still in DRAFT awaiting approval | JE000245 | DRAFT |
| 2000 | Accounts Payable | INV000026 | AP_INVOICE | 7967875.84 | Invoice approved in the AP sub-ledger; GL journal still in DRAFT awaiting approval | JE000518 | DRAFT |

### GL postings by source module

```sql
SELECT source_module, COUNT(DISTINCT je_id) AS journals, ROUND(SUM(debit_inr) / 1e7, 2) AS debits_inr_cr
FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_gl GROUP BY source_module ORDER BY source_module
```

| source_module | journals | debits_inr_cr |
|---|---|---|
| AP | 882 | 924.32 |
| AR | 490 | 312.8 |
| GL | 519 | 381.59 |
