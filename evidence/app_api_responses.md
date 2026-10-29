# App API responses

_Collected 2026-10-29 12:33 UTC from `https://cfo-fna-control-tower-dev-7474646051057767.aws.databricksapps.com` with a Bearer token (masked)._

## `GET /api/health` → 200

```json
{
  "status": "healthy",
  "app": "finance-operations"
}
```

## `GET /api/debug/status` → 200

```json
{
  "demo_mode": false,
  "auth_mode": "obo",
  "db": {
    "demo_mode": false,
    "live": true,
    "last_error": null,
    "last_success_at": "2026-10-29T12:29:59+00:00",
    "last_failure_at": null,
    "auth_mode": "sp",
    "warehouse_id": "87c76aa3893e6472",
    "catalog": "akash_fevm_ts_catalog",
    "schema": "finance_ops_control_tower"
  },
  "lakebase": {
    "demo_mode": false,
    "init_error": null,
    "host": "ep-still-math-d2odnn98.database.us-east-1.cloud.databricks.com",
    "user": "dcb547fd-b9e5-44ff-a339-e7723f5016bd",
    "instance": "fna-control-tower-db",
    "database": "databricks_postgres",
    "connected": true,
    "queue_table": "finance_ops_control_tower.ap_exception_queue",
    "in_memory_chat_rows": 0
  },
  "genie": {
    "configured": true,
    "space_id": "01f1d38f62131010a21422b74b92e9e6",
    "mas_endpoint": null,
    "chat_route": "genie"
  },
  "escalate": {
    "alert_id": null,
    "dest_id": null,
    "recipient": "demo.user@example.com",
    "sql_cached": false
  }
}
```

## `GET /api/metrics/p2p` → 200

```json
{
  "metrics": {
    "total_invoices": 550,
    "matched": 190,
    "touchless": 189,
    "release_blocked": 3,
    "release_blocked_amount": 28673573.210000005,
    "two_way": 188,
    "amount_mismatch": 99,
    "no_po": 73,
    "extraction_mismatch": 3,
    "exceptions": 407,
    "exceptions_by_type": {
      "MISSING_GRN": 188,
      "AMOUNT_MISMATCH": 98,
      "EXTRACTION_MISMATCH": 3,
      "CRITICAL_OVERDUE": 16,
      "MISSING_GSTIN": 3,
      "NO_PO_REFERENCE": 72,
      "DUPLICATE": 27
    },
    "overdue_count": 454,
    "total_amount": 5816091409.249999,
    "overdue_amount": 4762073313.969999,
    "avg_aging_days": 58.0,
    "touchless_rate": 34.4
  },
  "payment_run": {
    "total_payments": 382,
    "total_paid": 3925603618.1,
    "avg_dpo": 36.1,
    "early_payments": 240,
    "on_time_payments": 7,
    "late_payments": 135
  }
}
```

## `GET /api/metrics/o2c` → 200

```json
{
  "metrics": {
    "total_outstanding": 173682290.84,
    "avg_dso": 59.4,
    "total_invoices": 262,
    "collected": 223,
    "total_collected": 1474110419.16,
    "overdue_count": 14,
    "cei": 88.9,
    "aging_buckets": [
      {
        "bucket": "0-30 days",
        "count": 19,
        "amount": 88731850.46000001
      },
      {
        "bucket": "31-60 days",
        "count": 9,
        "amount": 26106262.61
      },
      {
        "bucket": "61-90 days",
        "count": 6,
        "amount": 23294907.77
      },
      {
        "bucket": "90+ days",
        "count": 5,
        "amount": 35549270.0
      }
    ],
    "customers_at_risk": [
      {
        "name": "Banerjee Inc",
        "credit_limit": 500000.0,
        "outstanding": 12376430.0,
        "utilization": 2475.3,
        "overdue": 1,
        "dso": 45.5
      },
      {
        "name": "Dhillon Inc",
        "credit_limit": 500000.0,
        "outstanding": 6845180.0,
        "utilization": 1369.0,
        "overdue": 1,
        "dso": 32.8
      },
      {
        "name": "Bhakta-Mitra",
        "credit_limit": 1000000.0,
        "outstanding": 8417825.0,
        "utilization": 841.8,
        "overdue": 0,
        "dso": 90.0
      },
      {
        "name": "Sarin, Raj and Mane",
        "credit_limit": 500000.0,
        "outstanding": 3424360.0,
        "utilization": 684.9,
        "overdue": 1,
        "dso": 14.0
      },
      {
        "name": "Din Ltd",
        "credit_limit": 1000000.0,
        "outstanding": 6127740.0,
        "utilization": 612.8,
        "overdue": 0,
        "dso": 23.8
      },
      {
        "name": "Barad Group",
        "credit_limit": 2000000.0,
        "outstanding": 8177105.0,
        "utilization": 408.9,
        "overdue": 1,
        "dso": 47.3
      },
      {
        "name": "Bajaj-Kapur",
        "credit_limit": 1000000.0,
        "outstanding": 3717000.0,
        "utilization": 371.7,
        "overdue": 0,
        "dso": 9.5
      },
      {
        "name": "Sahota-Tank",
        "credit_limit": 1000000.0,
        "outstanding": 3645020.0,
        "utilization": 364.5,
        "overdue": 0,
        "dso": 17.9
      },
      {
        "name": "Nagarajan, More and Thakkar",
        "credit_limit": 2000000.0,
        "outstanding": 6629830.0,
        "utilization": 331.5,
        "overdue": 0,
        "dso": 34.0
      },
      {
        "name": "Mannan, Kari and Vohra",
        "credit_limit": 2000000.0,
        "outstanding": 6346040.0,
        "utilization": 317.3,
        "overdue": 1,
        "dso": 61.1
      }
    ]
  }
}
```

## `GET /api/metrics/r2r` → 200

```json
{
  "metrics": {
    "total_jes": 1891,
    "total_lines": 4561,
    "total_debits": 16187105683.439999,
    "total_credits": 16187105683.44,
    "posted": 1891,
    "pending": 0,
    "tb_total_debit": 6613033648.910002,
    "tb_total_credit": 6613033648.910001,
    "tb_imbalance": 9.5367431640625e-07,
    "is_balanced": true,
    "trial_balance": [
      {
        "account_code": "1000",
        "account_name": "Cash and Cash Equivalents",
        "account_type": "Asset",
        "debit": 103276070.13000001,
        "credit": 313205144.41,
        "balance": 257050957.41,
        "balance_type": "CR",
        "transactions": 77
      },
      {
        "account_code": "1100",
        "account_name": "Accounts Receivable",
        "account_type": "Asset",
        "debit": 102436685.0,
        "credit": 96467141.93,
        "balance": 158365890.84,
        "balance_type": "DR",
        "transactions": 32
      },
      {
        "account_code": "1300",
        "account_name": "Prepaid Expenses",
        "account_type": "Asset",
        "debit": 18650783.67,
        "credit": 0.0,
        "balance": 71219879.38,
        "balance_type": "DR",
        "transactions": 7
      },
      {
        "account_code": "1500",
        "account_name": "Property Plant Equipment",
        "account_type": "Asset",
        "debit": 17056559.49,
        "credit": 0.0,
        "balance": 96690953.65,
        "balance_type": "DR",
        "transactions": 6
      },
      {
        "account_code": "1600",
        "account_name": "Accumulated Depreciation",
        "account_type": "Asset",
        "debit": 0.0,
        "credit": 1049238.07,
        "balance": 66644649.75,
        "balance_type": "CR",
        "transactions": 1
      },
      {
        "account_code": "2000",
        "account_name": "Accounts Payable",
        "account_type": "Liability",
        "debit": 239666343.93999997,
        "credit": 872896543.8699999,
        "balance": 1773711024.54,
        "balance_type": "CR",
        "transactions": 100
      },
      {
        "account_code": "2100",
        "account_name": "Accrued Expenses",
        "account_type": "Liability",
        "debit": 3791917.71,
        "credit": 10520239.79,
        "balance": 179248565.21,
        "balance_type": "CR",
        "transactions": 7
      },
      {
        "account_code": "2200",
        "account_name": "Short Term Debt",
        "account_type": "Liability",
        "debit": 0.0,
        "credit": 6417568.41,
        "balance": 70457826.86,
        "balance_type": "CR",
        "transactions": 2
      },
      {
        "account_code": "2600",
        "account_name": "GST Payable",
        "account_type": "Liability",
        "debit": 0.0,
        "credit": 15625935.0,
        "balance": 250657605.0,
        "balance_type": "CR",
        "transactions": 15
      },
      {
        "account_code": "3000",
        "account_name": "Share Capital",
        "account_type": "Equity",
        "debit": 0.0,
        "credit": 0.0,
        "balance": 2500000000.0,
        "balance_type": "CR",
        "transactions": 0
      },
      {
        "account_code": "4000",
        "account_name": "Product Revenue",
        "account_type": "Revenue",
        "debit": 0.0,
        "credit": 29083500.0,
        "balance": 650994750.0,
        "balance_type": "CR",
        "transactions": 5
      },
      {
        "account_code": "4100",
        "account_name": "Service Revenue",
        "account_type": "Revenue",
        "debit": 0.0,
        "credit": 57727250.0,
        "balance": 741547500.0,
        "balance_type": "CR",
        "transactions": 10
      },
      {
        "account_code": "4200",
        "account_name": "Other Income",
        "account_type": "Revenue",
        "debit": 0.0,
        "credit": 7925659.789999999,
        "balance": 122720770.14,
        "balance_type": "CR",
        "transactions": 4
      },
      {
        "account_code": "5000",
        "account_name": "Cost of Goods Sold",
        "account_type": "Expense",
        "debit": 126825326.99000001,
        "credit": 0.0,
        "balance": 627810999.07,
        "balance_type": "DR",
        "transactions": 10
      },
      {
        "account_code": "5100",
        "account_name": "Salaries and Wages",
        "account_type": "Expense",
        "debit": 54622461.45999999,
        "credit": 0.0,
        "balance": 612562548.5,
        "balance_type": "DR",
        "transactions": 10
      },
      {
        "account_code": "5200",
        "account_name": "Rent Expense",
        "account_type": "Expense",
        "debit": 56467824.15,
        "credit": 0.0,
        "balance": 545707817.36,
        "balance_type": "DR",
        "transactions": 7
      },
      {
        "account_code": "5300",
        "account_name": "Utilities Expense",
        "account_type": "Expense",
        "debit": 105482834.49,
        "credit": 0.0,
        "balance": 700125663.26,
        "balance_type": "DR",
        "transactions": 11
      },
      {
        "account_code": "5400",
        "account_name": "Marketing Expense",
        "account_type": "Expense",
        "debit": 223795722.57999998,
        "credit": 0.0,
        "balance": 856566271.55,
        "balance_type": "DR",
        "transactions": 18
      },
      {
        "account_code": "5500",
        "account_name": "IT Expense",
        "account_type": "Expense",
        "debit": 57357267.63,
        "credit": 0.0,
        "balance": 650642957.0,
        "balance_type": "DR",
        "transactions": 9
      },
      {
        "account_code": "5600",
        "account_name": "Travel Expense",
        "account_type": "Expense",
        "debit": 77115792.23,
        "credit": 0.0,
        "balance": 696673172.35,
        "balance_type": "DR",
        "transactions": 7
      },
      {
        "account_code": "5650",
        "account_name": "Bad Debt Expense",
        "account_type": "Expense",
        "debit": 7534300.0,
        "credit": 0.0,
      
```

## `GET /api/recon` → 200

```json
{
  "rows": [
    {
      "account_code": "1100",
      "account_name": "Accounts Receivable",
      "subledger_source": "silver_o2c_invoices less bronze_o2c_payments (gold_fact_collections.balance_outstanding)",
      "subledger_amount": 173682290.84,
      "gl_amount": 158365890.84,
      "delta": 15316400.0,
      "reconciling_items_amount": 15316400.0,
      "reconciling_items_count": 3,
      "unexplained_delta": 0.0,
      "tied": true,
      "cutoff_date": "2026-10-29",
      "items": [
        {
          "document_id": "CINV000130",
          "document_type": "AR_INVOICE",
          "amount": 851960.0,
          "reason": "Invoice posted in the AR sub-ledger; GL journal still in DRAFT awaiting approval",
          "gl_je_id": "JE000132",
          "gl_je_status": "DRAFT"
        },
        {
          "document_id": "CINV000157",
          "document_type": "AR_INVOICE",
          "amount": 1213335.0,
          "reason": "Invoice posted in the AR sub-ledger; GL journal still in DRAFT awaiting approval",
          "gl_je_id": "JE000159",
          "gl_je_status": "DRAFT"
        },
        {
          "document_id": "CINV000242",
          "document_type": "AR_INVOICE",
          "amount": 13251105.0,
          "reason": "Invoice posted in the AR sub-ledger; GL journal still in DRAFT awaiting approval",
          "gl_je_id": "JE000245",
          "gl_je_status": "DRAFT"
        }
      ]
    },
    {
      "account_code": "2000",
      "account_name": "Accounts Payable",
      "subledger_source": "silver_p2p_invoices less completed bronze_p2p_payments (gold_fact_invoices)",
      "subledger_amount": 1781678900.38,
      "gl_amount": 1773711024.54,
      "delta": 7967875.84,
      "reconciling_items_amount": 7967875.84,
      "reconciling_items_count": 1,
      "unexplained_delta": 0.0,
      "tied": true,
      "cutoff_date": "2026-10-29",
      "items": [
        {
          "document_id": "INV000026",
          "document_type": "AP_INVOICE",
          "amount": 7967875.84,
          "reason": "Invoice approved in the AP sub-ledger; GL journal still in DRAFT awaiting approval",
          "gl_je_id": "JE000518",
          "gl_je_status": "DRAFT"
        }
      ]
    }
  ],
  "all_tied": true
}
```

## `GET /api/verify-invoice/INV000198` → 200

```json
{
  "invoice_id": "INV000198",
  "invoice_number": "VINV-2026-10198",
  "vendor_name": "Dar, Raj and Wagle",
  "release_blocked": true,
  "block_reason": "PDF total differs from ERP total",
  "erp_total": 7454589.9,
  "pdf_total": 7976411.19,
  "checks": [
    {
      "id": 1,
      "name": "Invoice \u2194 PO total",
      "status": "FAIL",
      "detail": "\u20b90.75 Cr vs \u20b90.63 Cr (18.0% variance, threshold 5%)"
    },
    {
      "id": 2,
      "name": "AI release control (PDF \u2194 ERP total)",
      "status": "FAIL",
      "detail": "RELEASE BLOCKED \u2014 PDF total differs from ERP total; PDF \u20b97,976,411 vs ERP \u20b97,454,590"
    },
    {
      "id": 3,
      "name": "ERP vendor \u2194 PDF vendor",
      "status": "PASS",
      "detail": "'Dar, Raj and Wagle' matches PDF"
    },
    {
      "id": 4,
      "name": "GSTIN match",
      "status": "PASS",
      "detail": "07IDWIZ3375D1ZK \u2713"
    },
    {
      "id": 5,
      "name": "PO reference match",
      "status": "PASS",
      "detail": "PO00309 \u2713"
    },
    {
      "id": 6,
      "name": "Vendor master integrity",
      "status": "PASS",
      "detail": "vendor record consistent"
    },
    {
      "id": 7,
      "name": "Duplicate payment check",
      "status": "PASS",
      "detail": "no duplicates in last 90 days"
    },
    {
      "id": 8,
      "name": "AP sub-ledger \u2194 GL tie-out",
      "status": "PASS",
      "detail": "tied: \u0394 \u20b97,967,876 fully explained by 1 reconciling item(s)"
    }
  ],
  "recommendation": {
    "label": "HOLD",
    "tone": "danger",
    "reason": "Payment release blocked by the AI control: PDF total differs from ERP total"
  }
}
```

## `GET /api/ap/exception-queue?limit=5` → 200

```json
{
  "source": "lakebase",
  "rows": [
    {
      "invoice_id": "INV942298",
      "invoice_number": "VINV-2026-10355",
      "vendor_id": "VND0097",
      "vendor_name": "Singh-Warrior",
      "legal_entity": "MERIDIAN-IN",
      "invoice_date": "2026-02-04",
      "due_date": "2026-02-19",
      "invoice_total_inr": 22904800.52,
      "match_status": "DUPLICATE",
      "exception_type": "DUPLICATE",
      "release_blocked": true,
      "block_reason": "Duplicate of INV000355",
      "ai_extracted_amount": null,
      "pdf_file_path": null,
      "aging_days": 267,
      "last_action": null,
      "last_action_by": null,
      "last_action_at": null
    },
    {
      "invoice_id": "INV945045",
      "invoice_number": "VINV-2026-10422",
      "vendor_id": "VND0022",
      "vendor_name": "Lalla PLC",
      "legal_entity": "MERIDIAN-IN",
      "invoice_date": "2026-07-28",
      "due_date": "2026-08-27",
      "invoice_total_inr": 21460710.65,
      "match_status": "DUPLICATE",
      "exception_type": "DUPLICATE",
      "release_blocked": true,
      "block_reason": "Duplicate of INV000422",
      "ai_extracted_amount": null,
      "pdf_file_path": null,
      "aging_days": 93,
      "last_action": null,
      "last_action_by": null,
      "last_action_at": null
    },
    {
      "invoice_id": "INV998821",
      "invoice_number": "VINV-2026-10471",
      "vendor_id": "VND0022",
      "vendor_name": "Lalla PLC",
      "legal_entity": "MERIDIAN-IN",
      "invoice_date": "2026-03-13",
      "due_date": "2026-04-12",
      "invoice_total_inr": 21076669.03,
      "match_status": "DUPLICATE",
      "exception_type": "DUPLICATE",
      "release_blocked": true,
      "block_reason": "Duplicate of INV000471",
      "ai_extracted_amount": null,
      "pdf_file_path": null,
      "aging_days": 230,
      "last_action": null,
      "last_action_by": null,
      "last_action_at": null
    },
    {
      "invoice_id": "INV910135",
      "invoice_number": "VINV-2026-10530",
      "vendor_id": "VND0078",
      "vendor_name": "Kothari-Subramaniam",
      "legal_entity": "MERIDIAN-IN",
      "invoice_date": "2026-01-13",
      "due_date": "2026-01-28",
      "invoice_total_inr": 19424406.06,
      "match_status": "DUPLICATE",
      "exception_type": "DUPLICATE",
      "release_blocked": true,
      "block_reason": "Duplicate of INV000530",
      "ai_extracted_amount": null,
      "pdf_file_path": null,
      "aging_days": 289,
      "last_action": null,
      "last_action_by": null,
      "last_action_at": null
    },
    {
      "invoice_id": "INV970192",
      "invoice_number": "VINV-2026-10163",
      "vendor_id": "VND0045",
      "vendor_name": "Saini, Babu and Khosla",
      "legal_entity": "MERIDIAN-UK",
      "invoice_date": "2026-04-08",
      "due_date": "2026-05-08",
      "invoice_total_inr": 19160258.19,
      "match_status": "DUPLICATE",
      "exception_type": "DUPLICATE",
      "release_blocked": true,
      "block_reason": "Duplicate of INV000163",
      "ai_extracted_amount": null,
      "pdf_file_path": null,
      "aging_days": 204,
      "last_action": null,
      "last_action_by": null,
      "last_action_at": null
    }
  ]
}
```

## `GET /api/summary/P2P` → 200

```json
{
  "tab": "P2P",
  "bullets": [
    "- 454 invoices overdue worth \u20b9476 Cr require immediate action",
    "- **Mane-Dugar** leads overdue exposure at \u20b923 Cr across 18 invoices",
    "- 188 invoices blocked on missing GRN; 98 have amount mismatches",
    "- Mann-Mittal** and **Pradhan, Patla and **Rattan** each show 5 mismatches"
  ],
  "as_of": "2026-10-29T12:34:24.897499+00:00",
  "signals": {
    "total_invoices": 550,
    "touchless": 189,
    "release_blocked": 3,
    "overdue_count": 454,
    "overdue_value_cr": 476.21,
    "exceptions_json": [
      {
        "type": "DUPLICATE",
        "count": 27
      },
      {
        "type": "AMOUNT_MISMATCH",
        "count": 98
      },
      {
        "type": "NO_PO_REFERENCE",
        "count": 72
      },
      {
        "type": "CRITICAL_OVERDUE",
        "count": 16
      },
      {
        "type": "MISSING_GSTIN",
        "count": 3
      },
      {
        "type": "MISSING_GRN",
        "count": 188
      },
      {
        "type": "EXTRACTION_MISMATCH",
        "count": 3
      }
    ],
    "top_vendors_json": [
      {
        "vendor": "Mane-Dugar",
        "overdue_count": 18,
        "overdue_value_cr": 22.85
      },
      {
        "vendor": "Lalla PLC",
        "overdue_count": 10,
        "overdue_value_cr": 20.16
      },
      {
        "vendor": "Bala, Chacko and Sangha",
        "overdue_count": 8,
        "overdue_value_cr": 13.26
      }
    ],
    "top_mismatch_json": [
      {
        "vendor": "Mann-Mittal",
        "mismatches": 5
      },
      {
        "vendor": "Pradhan, Patla and Rattan",
        "mismatches": 5
      },
      {
        "vendor": "Merchant-Merchant",
        "mismatches": 4
      }
    ]
  }
}
```

## `POST /api/approve` → 200

```json
{
  "status": "logged",
  "action": "REJECT",
  "invoice_id": "INV000198",
  "persisted_to": "lakebase"
}
```

## `POST /api/call-log` → 200

```json
{
  "status": "logged",
  "outcome": "PTP"
}
```

## `POST /api/chat` → 200

```json
data: {"type": "chunk", "text": "You want to see the list of invoices tha"}

data: {"type": "chunk", "text": "t were blocked because their PDF details"}

data: {"type": "chunk", "text": " do not match the ERP system. The list i"}

data: {"type": "chunk", "text": "ncludes invoice ID, vendor name, invoice"}

data: {"type": "chunk", "text": " total amount in INR, AI extracted amoun"}

data: {"type": "chunk", "text": "t, and the reason for blocking, sorted b"}

data: {"type": "chunk", "text": "y the invoice total amount in descending"}

data: {"type": "chunk", "text": " order.\n\n**3 invoices** are blocked beca"}

data: {"type": "chunk", "text": "use the **PDF total differs from the ERP"}

data: {"type": "chunk", "text": " total**. Examples include:\n- **INV00020"}

data: {"type": "chunk", "text": "4** \u2014 **Srivastava-Misra**: ERP total **"}

data: {"type": "chunk", "text": "\u20b91.77 Cr** vs PDF-extracted amount **\u20b91."}

data: {"type": "chunk", "text": "70 Cr**\n- **INV000198** \u2014 **Dar, Raj and"}

data: {"type": "chunk", "text": " Wagle**: ERP total **\u20b974.55 L** vs PDF-"}

data: {"type": "chunk", "text": "extracted amount **\u20b979.76 L**\n- **INV000"}

data: {"type": "chunk", "text": "128** \u2014 **Kant, Sehgal and Prasad**: ERP"}

data: {"type": "chunk", "text": " total **\u20b935.42 L** vs PDF-extracted amo"}

data: {"type": "chunk", "text": "unt **\u20b939.31 L**\nThe largest blocked inv"}

data: {"type": "chunk", "text": "oice in this result is **INV000204** at "}

data: {"type": "chunk", "text": "**\u20b91.77 Cr**.\n\n| invoice_id | vendor_nam"}

data: {"type": "chunk", "text": "e | invoice_total_inr | ai_extracted_amo"}

data: {"type": "chunk", "text": "unt | block_reason |\n|---|---|---|---|--"}

data: {"type": "chunk", "text": "-|\n| INV000204 | Srivastava-Misra | 17,6"}

data: {"type": "chunk", "text": "77,178 | 16,970,091 | PDF total differs "}

data: {"type": "chunk", "text": "from ERP total |\n| INV000198 | Dar, Raj "}

data: {"type": "chunk", "text": "and Wagle | 7,454,590 | 7,976,411 | PDF "}

data: {"type": "chunk", "text": "total differs from ERP total |\n| INV0001"}

data: {"type": "chunk", "text": "28 | Kant, Sehgal and Prasad | 3,541,806"}

data: {"type": "chunk", "text": " | 3,931,404 | PDF total differs from ER"}

data: {"type": "chunk", "text": "P total |\n"}

data: {"type": "done", "session_id": "ba79cb5f-9e28-4537-b7a0-a100282956b4", "previous_response_id": "genie:01f1d39516551c9598d9c20f9cd520e4", "routing": {"domain": "Finance Agent", "route": "genie", "explanation": "Genie Agent (Conversation API)", "tool": "genie", "auth": "obo", "row_count": 3}, "agent": "genie-space:01f1d38f62131010a21422b74b92e9e6", "sql": "SELECT `invoice_id`, `vendor_name`, `invoice_total_inr`, `ai_extracted_amount`, `block_reason` FROM `akash_fevm_ts_catalog`.`finance_ops_control_tower`.`gold_fact_invoices` WHERE `release_blocked` = true ORDER BY `invoice_total_inr` DESC"}


```

## `GET /api/ap/exception-queue/INV000198` → 200

```json
{
  "source": "lakebase",
  "row": {
    "invoice_id": "INV000198",
    "invoice_number": "VINV-2026-10198",
    "vendor_id": "VND0074",
    "vendor_name": "Dar, Raj and Wagle",
    "legal_entity": "MERIDIAN-UK",
    "invoice_date": "2026-09-18",
    "due_date": "2026-11-17",
    "invoice_total_inr": 7454589.9,
    "match_status": "THREE_WAY_MATCHED",
    "exception_type": "EXTRACTION_MISMATCH",
    "release_blocked": true,
    "block_reason": "PDF total differs from ERP total",
    "ai_extracted_amount": 7976411.19,
    "pdf_file_path": "dbfs:/Volumes/akash_fevm_ts_catalog/finance_ops_control_tower/raw_invoices/INV000198.pdf",
    "aging_days": 41,
    "last_action": "REJECT",
    "last_action_by": "akash.s@databricks.com",
    "last_action_at": "2026-10-29T12:34:26.600627"
  }
}
```
