# Genie transcripts

_Collected 2026-10-29 12:24 UTC through the Genie Conversation API, space `01f1d38f62131010a21422b74b92e9e6`._

## 1. AP lead: What is our touchless invoice rate, and how many invoices are release-blocked?

**Status:** COMPLETED

**Answer:** You want to know the percentage of invoices that are processed without manual intervention (touchless) and the total number of invoices that are blocked from release due to discrepancies.
**Touchless invoice rate:** **34.36%**. **Release-blocked invoices:** **3**; based on the single result returned, about one-third of invoices are touchless while 3 invoices are currently release-blocked.

```sql
SELECT try_divide(100.0 * SUM(CASE WHEN `is_touchless` = true THEN 1 ELSE 0 END),COUNT(*)) AS `touchless_invoice_rate_pct`, SUM(CASE WHEN `release_blocked` = true THEN 1 ELSE 0 END) AS `release_blocked_invoices` FROM `akash_fevm_ts_catalog`.`finance_ops_control_tower`.`gold_fact_invoices`
```

| touchless_invoice_rate_pct | release_blocked_invoices |
|---|---|
| 34.36363636363636 | 3 |

## 2. AP lead: Which invoices were blocked because the PDF disagrees with the ERP?

**Status:** COMPLETED

**Answer:** You want to see the list of invoices that were blocked because their PDF details disagree with the ERP system.
There are **3 blocked invoices** in the results, and all were blocked because the **PDF total differs from the ERP total**.

- **VINV-2026-10204** from **Srivastava-Misra** — ERP total **₹1.77 Cr** vs PDF-extracted amount **₹1.70 Cr**
- **VINV-2026-10198** from **Dar, Raj and Wagle** — ERP total **₹74.55 L** vs PDF-extracted amount **₹79.76 L**
- **VINV-2026-10128** from **Kant, Sehgal and Prasad** — ERP total **₹35.42 L** vs PDF-extracted amount **₹39.31 L**

In this result set, every blocked invoice is tied to a **total amount mismatch** between the PDF and the ERP.

```sql
SELECT `invoice_id`, `invoice_number`, `vendor_name`, `invoice_total_inr`, `ai_extracted_amount`, `block_reason` FROM `akash_fevm_ts_catalog`.`finance_ops_control_tower`.`gold_fact_invoices` WHERE `release_blocked` = true ORDER BY `invoice_total_inr` DESC
```

| invoice_id | invoice_number | vendor_name | invoice_total_inr | ai_extracted_amount | block_reason |
|---|---|---|---|---|---|
| INV000204 | VINV-2026-10204 | Srivastava-Misra | 1.767717762E7 | 1.697009052E7 | PDF total differs from ERP total |
| INV000198 | VINV-2026-10198 | Dar, Raj and Wagle | 7454589.9 | 7976411.19 | PDF total differs from ERP total |
| INV000128 | VINV-2026-10128 | Kant, Sehgal and Prasad | 3541805.69 | 3931404.32 | PDF total differs from ERP total |

## 3. Controller: Do AR and AP tie to the general ledger, and what explains any difference?

**Status:** COMPLETED

**Answer:** You want to see whether the accounts receivable (AR) and accounts payable (AP) sub-ledgers match the general ledger (GL) balances, and if there are any differences, what explains them.
**Yes** — both **AR** and **AP** tie to the general ledger as of **2026-10-29** because the **unexplained difference is ₹0** for both accounts.
- **Accounts Receivable:** Sub-ledger **₹17.37 Cr DR**, GL **₹15.84 Cr DR**; difference **₹1.53 Cr**, fully explained by **3** reconciling items.
- **Accounts Payable:** Sub-ledger **₹178.17 Cr CR**, GL **₹177.37 Cr CR**; difference **₹79.68 L**, fully explained by **1** reconciling item.
In both cases, the gap between sub-ledger and GL is fully accounted for by documented reconciling items, so the reconciliation is complete.

```sql
SELECT `account_code`, `account_name`, `balance_type`, `subledger_source`, `subledger_amount`, `gl_amount`, `delta`, `reconciling_items_amount`, `reconciling_items_count`, `unexplained_delta`, `tied`, `cutoff_date`
FROM `akash_fevm_ts_catalog`.`finance_ops_control_tower`.`gold_recon_subledger_vs_gl`
WHERE `account_code` IS NOT NULL
ORDER BY `account_code`
```

| account_code | account_name | balance_type | subledger_source | subledger_amount | gl_amount | delta | reconciling_items_amount | reconciling_items_count | unexplained_delta | tied | cutoff_date |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1100 | Accounts Receivable | DR | silver_o2c_invoices less bronze_o2c_payments (gold_fact_collections.balance_outs | 1.7368229084E8 | 1.5836589084E8 | 1.53164E7 | 1.53164E7 | 3 | 0.0 | true | 2026-10-29 |
| 2000 | Accounts Payable | CR | silver_p2p_invoices less completed bronze_p2p_payments (gold_fact_invoices) | 1.78167890038E9 | 1.77371102454E9 | 7967875.84 | 7967875.84 | 1 | 0.0 | true | 2026-10-29 |

## 4. Collections manager: Which five customers have the largest overdue receivables?

**Status:** COMPLETED

**Answer:** You want to see the top five customers who have the largest amounts of overdue receivables.
The five customers with the largest overdue receivables are:
- **Naidu-Gupta** — **₹1.21 Cr** overdue
- **Banerjee Inc** — **₹91.82 L** overdue
- **Barad Group** — **₹81.77 L** overdue
- **Dhillon Inc** — **₹68.45 L** overdue
- **Din-Sathe** — **₹63.80 L** overdue
The highest overdue amount is **Naidu-Gupta** at **₹1.21 Cr**, and all five customers each have more than **₹63 L** overdue.

```sql
WITH customer_overdue AS (
  SELECT
    `customer_id`,
    `customer_name`,
    SUM(`balance_outstanding`) AS `overdue_receivables_inr`
  FROM `akash_fevm_ts_catalog`.`finance_ops_control_tower`.`gold_fact_collections`
  WHERE `customer_id` IS NOT NULL
    AND `customer_name` IS NOT NULL
    AND `balance_outstanding` IS NOT NULL
    AND `days_overdue` IS NOT NULL
    AND `days_overdue` > 0
    AND `balance_outstanding` > 0
  GROUP BY `customer_id`, `customer_name`
), ranked AS (
  SELECT
    `customer_id`,
    `customer_name`,
    `overdue_receivables_inr`,
    RANK() OVER (ORDER BY `overdue_receivables_inr` DESC) AS `rnk`
  FROM customer_overdue
)
SELECT
  `customer_id`,
  `customer_name`,
  `overdue_receivables_inr`
FROM ranked
WHERE `rnk` <= 5
ORDER BY `overdue_receivables_inr` DESC, `customer_id`
```

| customer_id | customer_name | overdue_receivables_inr |
|---|---|---|
| CUS0087 | Naidu-Gupta | 1.208025E7 |
| CUS0026 | Banerjee Inc | 9181580.0 |
| CUS0003 | Barad Group | 8177105.0 |
| CUS0012 | Dhillon Inc | 6845180.0 |
| CUS0037 | Din-Sathe | 6380260.0 |

## 5. CFO: Give me a working capital snapshot: cash, receivables and payables from the latest trial balance.

**Status:** COMPLETED

**Answer:** You want to see a snapshot of working capital components from the latest trial balance, specifically cash, receivables, and payables.
Latest trial balance snapshot: **Cash is ₹25.71 Cr CR**, **Receivables are ₹15.84 Cr DR**, and **Payables are ₹202.44 Cr CR**. Across these 3 working-capital buckets, **payables are the largest balance by a wide margin**.

```sql
WITH `latest_period` AS (
  SELECT MAX(`period`) AS `period`
  FROM `akash_fevm_ts_catalog`.`finance_ops_control_tower`.`gold_fact_trial_balance`
  WHERE `period` IS NOT NULL
), `classified` AS (
  SELECT
    CASE
      WHEN `account_name` IS NOT NULL AND (`account_name` ILIKE '%cash%' OR `account_name` ILIKE '%bank%') THEN 'cash'
      WHEN `account_name` IS NOT NULL AND (`account_name` ILIKE '%receivable%' OR `account_name` ILIKE '%trade receivable%' OR `account_name` ILIKE '%accounts receivable%' OR `account_name` ILIKE '%debtors%') THEN 'receivables'
      WHEN `account_name` IS NOT NULL AND (`account_name` ILIKE '%payable%' OR `account_name` ILIKE '%trade payable%' OR `account_name` ILIKE '%accounts payable%' OR `account_name` ILIKE '%creditors%') THEN 'payables'
      WHEN `account_subtype` IS NOT NULL AND `account_subtype` ILIKE '%receivable%' THEN 'receivables'
      WHEN `account_subtype` IS NOT NULL AND `account_subtype` ILIKE '%payable%' THEN 'payables'
      WHEN `account_type` IS NOT NULL AND `account_type` ILIKE '%asset%' AND `account_name` IS NOT NULL AND (`account_name` ILIKE '%cash%' OR `account_name` ILIKE '%bank%') THEN 'cash'
      ELSE NULL
    END AS `working_capital_bucket`,
    SUM(CASE WHEN `balance_type` = 'DR' THEN `closing_balance_inr` WHEN `balance_type` = 'CR' THEN -`closing_balance_inr` ELSE 0 END) AS `signed_balance_inr`
  FROM `akash_fevm_ts_catalog`.`finance_ops_control_tower`.`gold_fact_trial_balance` tb
  INNER JOIN `latest_period` lp
    ON tb.`period` = lp.`period`
  WHERE tb.`period` IS NOT NULL
    AND tb.`account_name` IS NOT NULL
  GROUP BY
    CASE
      WHEN `account_name` IS NOT NULL AND (`account_name` ILIKE '%cash%' OR `account_name` ILIKE '%bank%') THEN 'cash'
      WHEN `account_name` IS NOT NULL AND (`account_name` ILIKE '%receivable%' OR `account_name` ILIKE '%trade receivable%' OR `account_name` ILIKE '%accounts receivable%' OR `account_name` ILIKE '%debtors%') THEN 'receivables'
      WHEN `account_name` IS NOT NULL AND (`account_name` ILIKE '%payable%' OR `account_name` ILIKE '%trade payable%' OR `account_name` ILIKE '%accounts payable%' OR `account_name` ILIKE '%creditors%') THEN 'payables'
      WHEN `account_subtype` IS NOT NULL AND `account_subtype` ILIKE '%receivable%' THEN 'receivables'
      WHEN `account_subtype` IS NOT NULL AND `account_subtype` ILIKE '%payable%' THEN 'payables'
      WHEN `account_type` IS NOT NULL AND `account_type` ILIKE '%asset%' AND `account_name` IS NOT NULL AND (`account_name` ILIKE '%cash%' OR `account_name` ILIKE '%bank%') THEN 'cash'
      ELSE NULL
    END
)
SELECT
  `working_capital_bucket`,
  ABS(`signed_balance_inr`) AS `closing_balance_inr`,
  CASE WHEN `signed_balance_inr` >= 0 THEN 'DR' ELSE 'CR' END AS `balance_type`
FROM `classified`
WHERE `working_capital_bucket` IS NOT NULL
ORDER BY `working_capital_bucket`
```

| working_capital_bucket | closing_balance_inr | balance_type |
|---|---|---|
| cash | 2.5705095741E8 | CR |
| payables | 2.02436862954E9 | CR |
| receivables | 1.5836589084E8 | DR |

## 6. Architect: How accurate is the AI invoice extraction?

**Status:** COMPLETED

**Answer:** You want to see the accuracy metrics of the AI invoice extraction from the most recent evaluation run.
The latest AI extraction evaluation shows **100% accuracy** on the measured invoice fields, based on **200** documents evaluated. Examples include:
- **Due date:** 100%
- **GSTIN:** 100%
- **Invoice number:** 100%
- **PO reference:** 100%
- **Total amount:** 100%
Tamper detection was also **100% precise and 100% complete**, catching **all 3 of 3** tampered documents with **0%** false positives.

```sql
SELECT `metric`, `value`
FROM `akash_fevm_ts_catalog`.`finance_ops_control_tower`.`gold_ai_extraction_eval`
WHERE `mlflow_run_id` = (
  SELECT max_by(`mlflow_run_id`, `evaluated_at`)
  FROM `akash_fevm_ts_catalog`.`finance_ops_control_tower`.`gold_ai_extraction_eval`
)
ORDER BY `metric`
```

| metric | value |
|---|---|
| accuracy_due_date | 1.0 |
| accuracy_gstin | 1.0 |
| accuracy_invoice_date | 1.0 |
| accuracy_invoice_number | 1.0 |
| accuracy_po_reference | 1.0 |
| accuracy_total | 1.0 |
| clean_blocked_false_positives | 0.0 |
| documents_evaluated | 200.0 |
| false_positive_rate | 0.0 |
| tamper_precision | 1.0 |
| tamper_recall | 1.0 |
| tampered_caught | 3.0 |
| tampered_documents | 3.0 |
