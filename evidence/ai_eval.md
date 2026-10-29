# AI extraction evaluation (F2)

Notebook `09_AI_Extraction_Evaluation.py`, setup run 5 task run `751824380370109`. Extraction runs inside the
pipeline (`silver_invoice_extractions`: `ai_parse_document` + `ai_extract`); the evaluation compares each field with
what the PDF actually prints (the ERP record, or the tampered total from `silver_pdf_corruption_log`).

- **MLflow experiment:** `/Users/akash.s@databricks.com/fna_control_tower_ai_extraction_eval`
- **MLflow run id:** `f6233b66d98c47d99e58cb7b938421bc` (metrics, parameters and the row-level table `eval_rows.json`)
- **UC table:** `gold_ai_extraction_eval` (one row per metric per run)

| Metric | Value |
|---|---|
| documents_evaluated | 200 |
| accuracy_total | 1.0 |
| accuracy_po_reference | 1.0 |
| accuracy_gstin | 1.0 |
| accuracy_invoice_number | 1.0 |
| accuracy_invoice_date | 1.0 |
| accuracy_due_date | 1.0 |
| tampered_documents | 3 |
| tampered_caught | 3 |
| tamper_recall | 1.0 |
| tamper_precision | 1.0 |
| clean_blocked_false_positives | 0 |
| false_positive_rate | 0.0 |

## Tampered invoices

| Invoice | Tamper | ERP status without the control | Result |
|---|---|---|---|
| INV000198 | PDF total +7% | THREE_WAY_MATCHED, would have been paid touchless | release_blocked |
| INV000128 | PDF total +11% | NO_PO_REFERENCE | release_blocked |
| INV000204 | PDF total −4% | AMOUNT_MISMATCH | release_blocked |

## Guardrail found during testing

In run 3 GSTIN accuracy was 0.765: for foreign vendors, whose PDFs print no GSTIN, `ai_extract` returned an invented
numeric string. The pipeline now keeps an extracted GSTIN only when it matches the 15-character GSTIN format, and
otherwise reads the pattern from the parsed text. Accuracy rose to 1.0 with no change in tamper recall. The release
control never blocked on this field, because it compares GSTIN only when the ERP has one.

## Comparison with the earlier build

The earlier build compared the extracted total with the pre-tax `invoice_amount`: it flagged 14 clean invoices and
missed all 3 tampered PDFs. Comparing with the tax-inclusive `total_amount` gives 3 of 3 caught and 0 false positives.
