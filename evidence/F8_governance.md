# F8 — Unity Catalog governance

_Collected 2026-10-29 12:32 UTC from `https://fevm-akash-fevm-ts.cloud.databricks.com`, `akash_fevm_ts_catalog.finance_ops_control_tower`._

### Grants on the schema

```sql
SHOW GRANTS ON SCHEMA akash_fevm_ts_catalog.finance_ops_control_tower
```

| Principal | ActionType | ObjectType | ObjectKey |
|---|---|---|---|
| aswinjameschristy.nayagam@databricks.com | ALL PRIVILEGES | CATALOG | akash_fevm_ts_catalog |
| aswinjameschristy.nayagam@databricks.com | EXTERNAL USE SCHEMA | CATALOG | akash_fevm_ts_catalog |
| aswinjameschristy.nayagam@databricks.com | MANAGE | CATALOG | akash_fevm_ts_catalog |
| dcb547fd-b9e5-44ff-a339-e7723f5016bd | EXECUTE | SCHEMA | akash_fevm_ts_catalog.finance_ops_control_tower |
| dcb547fd-b9e5-44ff-a339-e7723f5016bd | SELECT | SCHEMA | akash_fevm_ts_catalog.finance_ops_control_tower |
| dcb547fd-b9e5-44ff-a339-e7723f5016bd | USE SCHEMA | SCHEMA | akash_fevm_ts_catalog.finance_ops_control_tower |
| mahendra.hemnani@databricks.com | ALL PRIVILEGES | CATALOG | akash_fevm_ts_catalog |
| mahendra.hemnani@databricks.com | EXTERNAL USE SCHEMA | CATALOG | akash_fevm_ts_catalog |
| mahendra.hemnani@databricks.com | MANAGE | CATALOG | akash_fevm_ts_catalog |
| yash.gupta@databricks.com | ALL PRIVILEGES | CATALOG | akash_fevm_ts_catalog |
| yash.gupta@databricks.com | EXTERNAL USE SCHEMA | CATALOG | akash_fevm_ts_catalog |
| yash.gupta@databricks.com | MANAGE | CATALOG | akash_fevm_ts_catalog |
| yash.gupta@databricks.com | READ METADATA | CATALOG | akash_fevm_ts_catalog |
| account users | READ METADATA | METASTORE | metastore_aws_us_east_1 |
| akash.s@databricks.com | ALL PRIVILEGES | CATALOG | akash_fevm_ts_catalog |
| akash.s@databricks.com | MANAGE | CATALOG | akash_fevm_ts_catalog |
| aec5be3d-de3c-404c-8e60-feed0f265fd3 | ALL PRIVILEGES | CATALOG | akash_fevm_ts_catalog |
| aec5be3d-de3c-404c-8e60-feed0f265fd3 | MANAGE | CATALOG | akash_fevm_ts_catalog |
| kanishk.jadhav@databricks.com | ALL PRIVILEGES | CATALOG | akash_fevm_ts_catalog |
| kanishk.jadhav@databricks.com | EXTERNAL USE SCHEMA | CATALOG | akash_fevm_ts_catalog |
| kanishk.jadhav@databricks.com | MANAGE | CATALOG | akash_fevm_ts_catalog |
| suraj.bang@databricks.com | READ METADATA | METASTORE | metastore_aws_us_east_1 |

### Row filter and column masks

```sql
SELECT table_name, column_name, mask_name FROM akash_fevm_ts_catalog.information_schema.column_masks WHERE table_schema = 'finance_ops_control_tower'
UNION ALL
SELECT table_name, filter_name, 'ROW FILTER on ' || target_columns FROM akash_fevm_ts_catalog.information_schema.row_filters WHERE table_schema = 'finance_ops_control_tower'
```

| table_name | column_name | mask_name |
|---|---|---|
| silver_invoice_extractions | extracted_ifsc | akash_fevm_ts_catalog.finance_ops_control_tower.mask_bank_account |
| silver_invoice_extractions | extracted_bank_account | akash_fevm_ts_catalog.finance_ops_control_tower.mask_bank_account |
| silver_invoice_extractions | extracted_gstin | akash_fevm_ts_catalog.finance_ops_control_tower.mask_gstin |
| gold_fact_invoices | akash_fevm_ts_catalog.finance_ops_control_tower.rf_legal_entity | ROW FILTER on legal_entity |
| gold_fact_collections | akash_fevm_ts_catalog.finance_ops_control_tower.rf_legal_entity | ROW FILTER on legal_entity |

### Governed tags (table level)

```sql
SELECT table_name, tag_name, tag_value FROM akash_fevm_ts_catalog.information_schema.table_tags WHERE schema_name = 'finance_ops_control_tower' ORDER BY 1, 2
```

| table_name | tag_name | tag_value |
|---|---|---|
| bronze_customers | fna_process | O2C |
| bronze_customers | fna_project | finance_ops_control_tower |
| bronze_je_lines | fna_process | R2R |
| bronze_je_lines | fna_project | finance_ops_control_tower |
| bronze_journal_entries | fna_process | R2R |
| bronze_journal_entries | fna_project | finance_ops_control_tower |
| bronze_p2p_invoices | fna_process | P2P |
| bronze_p2p_invoices | fna_project | finance_ops_control_tower |
| bronze_vendors | fna_process | P2P |
| bronze_vendors | fna_project | finance_ops_control_tower |
| gold_ap_exception_queue | fna_process | P2P |
| gold_ap_exception_queue | fna_project | finance_ops_control_tower |
| gold_dim_customer | fna_process | O2C |
| gold_dim_customer | fna_project | finance_ops_control_tower |
| gold_dim_vendor | fna_process | P2P |
| gold_dim_vendor | fna_project | finance_ops_control_tower |
| gold_fact_collections | fna_process | O2C |
| gold_fact_collections | fna_project | finance_ops_control_tower |
| gold_fact_gl | fna_process | R2R |
| gold_fact_gl | fna_project | finance_ops_control_tower |
| gold_fact_invoices | fna_process | P2P |
| gold_fact_invoices | fna_project | finance_ops_control_tower |
| gold_fact_payments | fna_process | P2P |
| gold_fact_payments | fna_project | finance_ops_control_tower |
| gold_fact_sales | fna_process | O2C |
| gold_fact_sales | fna_project | finance_ops_control_tower |
| gold_fact_trial_balance | fna_process | R2R |
| gold_fact_trial_balance | fna_project | finance_ops_control_tower |
| gold_recon_reconciling_items | fna_process | R2R |
| gold_recon_reconciling_items | fna_project | finance_ops_control_tower |
| gold_recon_subledger_vs_gl | fna_process | R2R |
| gold_recon_subledger_vs_gl | fna_project | finance_ops_control_tower |
| silver_duplicate_invoices | fna_process | P2P |
| silver_duplicate_invoices | fna_project | finance_ops_control_tower |
| silver_invoice_exceptions | fna_process | P2P |
| silver_invoice_exceptions | fna_project | finance_ops_control_tower |
| silver_invoice_extractions | fna_process | P2P |
| silver_invoice_extractions | fna_project | finance_ops_control_tower |
| silver_je_quarantine | fna_process | R2R |
| silver_je_quarantine | fna_project | finance_ops_control_tower |
| silver_o2c_invoices | fna_process | O2C |
| silver_o2c_invoices | fna_project | finance_ops_control_tower |
| silver_p2p_invoices | fna_process | P2P |
| silver_p2p_invoices | fna_project | finance_ops_control_tower |

### Governed tags (PII columns)

```sql
SELECT table_name, column_name, tag_name, tag_value FROM akash_fevm_ts_catalog.information_schema.column_tags WHERE schema_name = 'finance_ops_control_tower' ORDER BY 1, 2
```

| table_name | column_name | tag_name | tag_value |
|---|---|---|---|
| bronze_customers | contact_email | fna_pii | true |
| bronze_customers | gstin | fna_pii | true |
| bronze_vendors | bank_account | fna_pii | true |
| bronze_vendors | bank_ifsc | fna_pii | true |
| bronze_vendors | contact_email | fna_pii | true |
| bronze_vendors | gstin | fna_pii | true |
| gold_dim_vendor | gstin | fna_pii | true |
| gold_fact_invoices | gstin_vendor | fna_pii | true |
| silver_invoice_extractions | extracted_bank_account | fna_pii | true |
| silver_invoice_extractions | extracted_gstin | fna_pii | true |
| silver_invoice_extractions | extracted_ifsc | fna_pii | true |

### Group to legal-entity map

```sql
SELECT * FROM akash_fevm_ts_catalog.finance_ops_control_tower.gov_entity_access
```

| group_name | legal_entity |
|---|---|
| ap_analysts_in | MERIDIAN-IN |
| ap_analysts_uk | MERIDIAN-UK |

### As the presenter (member of finance_controllers): clear bank details, all entities

```sql
SELECT current_user() AS reader, is_member('finance_controllers') AS controller,
       (SELECT COUNT(DISTINCT legal_entity) FROM akash_fevm_ts_catalog.finance_ops_control_tower.gold_fact_invoices) AS entities_visible,
       (SELECT FIRST(extracted_bank_account) FROM akash_fevm_ts_catalog.finance_ops_control_tower.silver_invoice_extractions WHERE extracted_bank_account IS NOT NULL) AS sample_bank_account
```

| reader | controller | entities_visible | sample_bank_account |
|---|---|---|---|
| akash.s@databricks.com | true | 2 | BNK1547952981 |

### Same queries as a restricted identity (member of `ap_analysts_uk`, not of `finance_controllers`)

The presenter was temporarily removed from `finance_controllers` and added to `ap_analysts_uk`, the queries were
re-run, and membership was restored afterwards.

| reader | controller | uk_analyst | invoices_visible | entities_visible | ar_invoices_visible | bank_account_INV000198 | gstin_INV000198 |
|---|---|---|---|---|---|---|---|
| akash.s@databricks.com | false | true | 109 | MERIDIAN-UK | 69 | XXXX9401 | 07XXXXXXXX1ZK |

Through the app (on-behalf-of-user authorization, same restricted identity): `APP as restricted user: total_invoices 109 touchless 32` — the app shows only the UK
entity's invoices, because the row filter is evaluated for the signed-in user. As a controller the same endpoint
returns 550 invoices (`app_api_responses.md`).

### UC grants to groups

The finance groups are workspace-local (FEVM cannot create account groups), and Unity Catalog grants require account
principals, so `GRANT ... TO finance_controllers` fails with `PRINCIPAL_DOES_NOT_EXIST` (recorded in the
`governance_post` task output). Access per group is enforced by the row filter and masks (`is_member()`); the app's
service principal receives `USE CATALOG`, `USE SCHEMA`, `SELECT`, `EXECUTE` and `READ VOLUME` from
`setup/grant_app_access.py`, and is not a controller, so it sees masked values.
