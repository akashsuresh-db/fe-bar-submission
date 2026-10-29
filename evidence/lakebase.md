# Lakebase — operational serving and write-back

_Collected 2026-10-29 12:39 UTC directly from Postgres on instance `fna-control-tower-db` (`ep-still-math-d2odnn98.database.us-east-1.cloud.databricks.com`), database `databricks_postgres`._

## Gold → Lakebase: synced AP exception queue

The 30 release-blocked queue rows are the 27 duplicates and the 3 tampered invoices.

```sql
SELECT COUNT(*) AS rows, SUM(CASE WHEN release_blocked THEN 1 ELSE 0 END) AS release_blocked FROM "finance_ops_control_tower"."ap_exception_queue"
```

| rows | release_blocked |
|---|---|
| 407 | 30 |

```sql
SELECT exception_type, COUNT(*) FROM "finance_ops_control_tower"."ap_exception_queue" GROUP BY 1 ORDER BY 2 DESC
```

| exception_type | count |
|---|---|
| MISSING_GRN | 188 |
| AMOUNT_MISMATCH | 98 |
| NO_PO_REFERENCE | 72 |
| DUPLICATE | 27 |
| CRITICAL_OVERDUE | 16 |
| EXTRACTION_MISMATCH | 3 |
| MISSING_GSTIN | 3 |

```sql
SELECT invoice_id, vendor_name, legal_entity, invoice_total_inr, ai_extracted_amount, exception_type, block_reason FROM "finance_ops_control_tower"."ap_exception_queue" WHERE release_blocked ORDER BY invoice_id
```

| invoice_id | vendor_name | legal_entity | invoice_total_inr | ai_extracted_amount | exception_type | block_reason |
|---|---|---|---|---|---|---|
| INV000128 | Kant, Sehgal and Prasad | MERIDIAN-IN | 3541805.69 | 3931404.32 | EXTRACTION_MISMATCH | PDF total differs from ERP total |
| INV000198 | Dar, Raj and Wagle | MERIDIAN-UK | 7454589.9 | 7976411.19 | EXTRACTION_MISMATCH | PDF total differs from ERP total |
| INV000204 | Srivastava-Misra | MERIDIAN-IN | 17677177.62 | 16970090.52 | EXTRACTION_MISMATCH | PDF total differs from ERP total |
| INV910135 | Kothari-Subramaniam | MERIDIAN-IN | 19424406.06 |  | DUPLICATE | Duplicate of INV000530 |
| INV910915 | Bhagat, Shenoy and Bora | MERIDIAN-IN | 4784135.28 |  | DUPLICATE | Duplicate of INV000242 |
| INV913518 | Ranganathan PLC | MERIDIAN-IN | 5982449.41 |  | DUPLICATE | Duplicate of INV000244 |
| INV916369 | Gola-Mittal | MERIDIAN-UK | 14300413.63 |  | DUPLICATE | Duplicate of INV000082 |
| INV921171 | Bhagat, Shenoy and Bora | MERIDIAN-IN | 1157792.84 |  | DUPLICATE | Duplicate of INV000307 |
| INV921610 | Kumer, Prasad and Dua | MERIDIAN-IN | 119496.95 |  | DUPLICATE | Duplicate of INV000492 |
| INV925913 | Majumdar, Ranganathan and Jani | MERIDIAN-IN | 433813.76 |  | DUPLICATE | Duplicate of INV000343 |
| INV927657 | Khosla-Kar | MERIDIAN-IN | 9503694.95 |  | DUPLICATE | Duplicate of INV000183 |
| INV937017 | Sanghvi-Ramachandran | MERIDIAN-IN | 15785354.68 |  | DUPLICATE | Duplicate of INV000445 |
| INV942298 | Singh-Warrior | MERIDIAN-IN | 22904800.52 |  | DUPLICATE | Duplicate of INV000355 |
| INV944625 | Thakur-Mohan | MERIDIAN-IN | 8393218.05 |  | DUPLICATE | Duplicate of INV000318 |
| INV945045 | Lalla PLC | MERIDIAN-IN | 21460710.65 |  | DUPLICATE | Duplicate of INV000422 |
| INV948752 | Choudhury, Bakshi and Maharaj | MERIDIAN-IN | 2583063.03 |  | DUPLICATE | Duplicate of INV000134 |
| INV956276 | Pradhan, Patla and Rattan | MERIDIAN-UK | 1975412.74 |  | DUPLICATE | Duplicate of INV000072 |
| INV958147 | Wable, Sahota and Edwin | MERIDIAN-IN | 399787.99 |  | DUPLICATE | Duplicate of INV000461 |
| INV962471 | Mane-Dugar | MERIDIAN-IN | 11078050.71 |  | DUPLICATE | Duplicate of INV000310 |
| INV966259 | Uppal Ltd | MERIDIAN-IN | 8257069.46 |  | DUPLICATE | Duplicate of INV000188 |
| INV970192 | Saini, Babu and Khosla | MERIDIAN-UK | 19160258.19 |  | DUPLICATE | Duplicate of INV000163 |
| INV975412 | Chandra Inc | MERIDIAN-IN | 9699770.45 |  | DUPLICATE | Duplicate of INV000020 |
| INV976741 | Kumer, Prasad and Dua | MERIDIAN-IN | 18078378.68 |  | DUPLICATE | Duplicate of INV000114 |
| INV977776 | Iyer-Manne | MERIDIAN-IN | 15718472.21 |  | DUPLICATE | Duplicate of INV000479 |
| INV978845 | Raja Ltd | MERIDIAN-IN | 2012539.87 |  | DUPLICATE | Duplicate of INV000473 |
| INV979214 | Kari LLC | MERIDIAN-IN | 8564383.08 |  | DUPLICATE | Duplicate of INV000308 |
| INV982789 | Chopra, Seth and Thakur | MERIDIAN-IN | 2228382.13 |  | DUPLICATE | Duplicate of INV000395 |
| INV984662 | Kohli-Nori | MERIDIAN-IN | 8685110.23 |  | DUPLICATE | Duplicate of INV000482 |
| INV984861 | Yohannan and Sons | MERIDIAN-IN | 13947195.77 |  | DUPLICATE | Duplicate of INV000478 |
| INV998821 | Lalla PLC | MERIDIAN-IN | 21076669.03 |  | DUPLICATE | Duplicate of INV000471 |

## App → Lakebase: operational writes (scripted test through the app API)

```sql
SELECT id, invoice_id, action, reason, approved_by, approved_at FROM fna_app.ap_approvals ORDER BY id
```

| id | invoice_id | action | reason | approved_by | approved_at |
|---|---|---|---|---|---|
| 1 | INV000198 | REJECT | PDF total 7% above ERP; vendor asked to reissue | akash.s@databricks.com | 2026-10-29 12:27:32.555855 |
| 2 | INV000198 | REJECT | PDF total 7% above ERP; vendor asked to reissue | akash.s@databricks.com | 2026-10-29 12:34:26.600627 |

```sql
SELECT id, customer_id, customer_name, outcome, ptp_date, notes, logged_by, logged_at FROM fna_app.ar_call_logs ORDER BY id
```

| id | customer_id | customer_name | outcome | ptp_date | notes | logged_by | logged_at |
|---|---|---|---|---|---|---|---|
| 1 | CUS0001 | Scripted test customer | PTP | 2026-11-15 | Evidence run | akash.s@databricks.com | 2026-10-29 12:27:34.162018 |
| 2 | CUS0001 | Scripted test customer | PTP | 2026-11-15 | Evidence run | akash.s@databricks.com | 2026-10-29 12:34:28.299115 |

```sql
SELECT session_id, user_email, left(question, 60) AS question, left(answer, 60) AS answer, asked_at FROM fna_app.chat_history ORDER BY asked_at
```

| session_id | user_email | question | answer | asked_at |
|---|---|---|---|---|
| b1075dff-3f84-4b2a-9aeb-f8ecf3438a83 | akash.s@databricks.com | Which invoices were blocked because the PDF disagrees with t | You want to see the list of invoices that were blocked becau | 2026-10-29 12:27:52.122173 |
| ba79cb5f-9e28-4537-b7a0-a100282956b4 | akash.s@databricks.com | Which invoices were blocked because the PDF disagrees with t | You want to see the list of invoices that were blocked becau | 2026-10-29 12:34:44.869284 |

## Lakebase → Unity Catalog write-back (`10_Lakebase_Sync`, mode `writeback`)

The two approvals are the two scripted evidence runs against the app API; the row counts match Postgres above.

| uc_table | rows |
|---|---|
| ops_ap_approvals | 2 |
| ops_ar_call_logs | 2 |
| ops_chat_history | 2 |

| invoice_id | action | reason | approved_by | approved_at |
|---|---|---|---|---|
| INV000198 | REJECT | PDF total 7% above ERP; vendor asked to reissue | akash.s@databricks.com | 2026-10-29T12:27:32.555 |
| INV000198 | REJECT | PDF total 7% above ERP; vendor asked to reissue | akash.s@databricks.com | 2026-10-29T12:34:26.600 |
