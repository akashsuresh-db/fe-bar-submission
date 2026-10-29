# Databricks notebook source
# MAGIC %md
# MAGIC # Finance & Accounting Demo - Setup & Data Generation
# MAGIC
# MAGIC Generates the synthetic ERP extracts for P2P, O2C and R2R and lands them as **raw CSV files**
# MAGIC in the `raw_csv` volume (one folder per entity). No `bronze_*` table is written here: the
# MAGIC Lakeflow declarative pipeline (`01_DLT_Pipeline.py`) owns every bronze, silver and gold table.
# MAGIC
# MAGIC Data design (deterministic, `random.seed(42)`):
# MAGIC - Vendor invoices carry the vendor-master GSTIN (about 2% blank, to drive `MISSING_GSTIN`).
# MAGIC - About 5% of vendor invoices are re-submitted duplicates (same vendor and invoice number, new id).
# MAGIC - AR and AP statuses depend on document age, so open items have a realistic aging profile.
# MAGIC - The general ledger is **derived from the sub-ledgers**: every AR invoice, customer receipt,
# MAGIC   AP invoice and vendor payment posts a balanced journal. Manual journals never touch the
# MAGIC   control accounts 1100 (AR) and 2000 (AP).
# MAGIC - A small, documented set of reconciling items (sub-ledger documents whose GL journal is still
# MAGIC   in DRAFT) is written to `raw_csv/recon_seed_items` so the sub-ledger to GL reconciliation shows
# MAGIC   a non-zero delta that is fully explained.
# MAGIC
# MAGIC **Catalog**: `${catalog}`  **Schema**: `${schema}`

# COMMAND ----------

# MAGIC %pip install faker --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower_catalog")
dbutils.widgets.text("schema", "finance_and_accounting")
CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
RAW_CSV = f"/Volumes/{CATALOG}/{SCHEMA}/raw_csv"

# Volumes are created by 00a_Reset_Raw_Volumes; fail fast if it did not run.
dbutils.fs.ls(RAW_CSV)
print(f"Writing raw CSV extracts to {RAW_CSV}")

# COMMAND ----------

import random
from datetime import date, timedelta, datetime
from faker import Faker

fake = Faker('en_IN')  # Indian locale for GST realism
random.seed(42)
Faker.seed(42)

TODAY = date.today()
INGESTED_AT = str(datetime.now())
written = {}


def write_csv(entity: str, rows: list[dict]):
    """Land one entity as CSV under /raw_csv/<entity>/ (the pipeline's Auto Loader source)."""
    df = spark.createDataFrame(rows)
    (df.coalesce(1).write.mode("overwrite")
       .option("header", "true").option("escape", '"')
       .csv(f"{RAW_CSV}/{entity}"))
    written[entity] = len(rows)
    print(f"  {entity:<24} {len(rows):>6} rows")


def random_date(start_days_ago=730, end_days_ago=0):
    start = TODAY - timedelta(days=start_days_ago)
    end = TODAY - timedelta(days=end_days_ago)
    return start + timedelta(days=random.randint(0, (end - start).days))


def cap(d: date) -> date:
    """No document is dated in the future."""
    return min(d, TODAY)


def age(d: date) -> int:
    return (TODAY - d).days


def random_gstin():
    states = ["27", "29", "06", "07", "09", "33", "36", "19", "08", "24"]
    state = random.choice(states)
    pan = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=5)) + \
          ''.join(random.choices('0123456789', k=4)) + \
          random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    return f"{state}{pan}1Z{random.choice('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"


LEGAL_ENTITIES = ["MERIDIAN-IN", "MERIDIAN-UK"]

def pick_entity():
    return random.choices(LEGAL_ENTITIES, weights=[80, 20])[0]

# COMMAND ----------

# MAGIC %md ### Dimension: Vendors and Customers

# COMMAND ----------

VENDOR_COUNT = 100
CUSTOMER_COUNT = 150
PO_COUNT = 500
SO_COUNT = 600
INVOICE_COUNT = 550
GRN_COUNT = 480

vendor_categories = ["IT Services", "Manufacturing", "Logistics", "Consulting", "Raw Materials",
                     "Office Supplies", "Facilities", "Marketing", "Legal", "HR Services"]
payment_terms_options = ["NET30", "NET45", "NET60", "NET15", "NET90"]

vendors = []
for i in range(1, VENDOR_COUNT + 1):
    country = random.choices(["India", "USA", "UK", "Germany"], weights=[70, 15, 10, 5])[0]
    currency = "INR" if country == "India" else random.choice(["USD", "EUR", "GBP"])
    vendors.append({
        "vendor_id": f"VND{i:04d}",
        "vendor_name": fake.company(),
        "vendor_category": random.choice(vendor_categories),
        "contact_email": fake.company_email(),
        "contact_phone": fake.phone_number(),
        "address_line1": fake.street_address(),
        "city": fake.city(),
        "state": fake.state(),
        "country": country,
        "pincode": fake.postcode(),
        "gstin": random_gstin() if country == "India" else "",
        "pan": ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=5)) + ''.join(random.choices('0123456789', k=4)) + random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') if country == "India" else "",
        "payment_terms": random.choice(payment_terms_options),
        "currency": currency,
        "bank_account": fake.bban(),
        "bank_ifsc": f"{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))}0{random.randint(100000,999999)}" if country == "India" else "",
        "is_active": random.choices([True, False], weights=[95, 5])[0],
        "created_date": str(random_date(1000, 400)),
        "modified_date": str(random_date(400, 0)),
        "_ingested_at": INGESTED_AT,
        "_source_system": "ERP_SAP"
    })
vendor_by_id = {v["vendor_id"]: v for v in vendors}

customer_segments = ["Enterprise", "Mid-Market", "SMB", "Startup", "Government", "Non-Profit"]
industry_options = ["Technology", "Healthcare", "Retail", "BFSI", "Manufacturing", "Education", "Telecom"]

customers = []
for i in range(1, CUSTOMER_COUNT + 1):
    country = random.choices(["India", "USA", "UK", "Singapore"], weights=[65, 20, 10, 5])[0]
    customers.append({
        "customer_id": f"CUS{i:04d}",
        "customer_name": fake.company(),
        "segment": random.choice(customer_segments),
        "industry": random.choice(industry_options),
        "contact_email": fake.company_email(),
        "contact_phone": fake.phone_number(),
        "billing_address": fake.address().replace("\n", ", "),
        "city": fake.city(),
        "state": fake.state(),
        "country": country,
        "gstin": random_gstin() if country == "India" else "",
        "credit_limit": float(random.choice([500000, 1000000, 2000000, 5000000, 10000000])),
        "payment_terms": random.choice(payment_terms_options),
        "currency": "INR" if country == "India" else "USD",
        "account_manager": fake.name(),
        "legal_entity": "MERIDIAN-UK" if country == "UK" else pick_entity(),
        "is_active": random.choices([True, False], weights=[92, 8])[0],
        "created_date": str(random_date(1000, 300)),
        "modified_date": str(random_date(300, 0)),
        "_ingested_at": INGESTED_AT,
        "_source_system": "CRM_SALESFORCE"
    })
customer_by_id = {c["customer_id"]: c for c in customers}

# COMMAND ----------

# MAGIC %md ### Chart of Accounts & Cost Centers

# COMMAND ----------

def acct(code, name, typ, sub):
    return {"account_code": code, "account_name": name, "account_type": typ, "account_subtype": sub,
            "is_active": True, "_ingested_at": INGESTED_AT}

chart_of_accounts = [
    acct("1000", "Cash and Cash Equivalents", "Asset", "Current Asset"),
    acct("1100", "Accounts Receivable", "Asset", "Current Asset"),
    acct("1200", "Inventory", "Asset", "Current Asset"),
    acct("1300", "Prepaid Expenses", "Asset", "Current Asset"),
    acct("1500", "Property Plant Equipment", "Asset", "Fixed Asset"),
    acct("1600", "Accumulated Depreciation", "Asset", "Fixed Asset"),
    acct("2000", "Accounts Payable", "Liability", "Current Liability"),
    acct("2100", "Accrued Expenses", "Liability", "Current Liability"),
    acct("2200", "Short Term Debt", "Liability", "Current Liability"),
    acct("2500", "Long Term Debt", "Liability", "Non-Current Liability"),
    acct("2600", "GST Payable", "Liability", "Tax Liability"),
    acct("3000", "Share Capital", "Equity", "Equity"),
    acct("3100", "Retained Earnings", "Equity", "Equity"),
    acct("4000", "Product Revenue", "Revenue", "Operating Revenue"),
    acct("4100", "Service Revenue", "Revenue", "Operating Revenue"),
    acct("4200", "Other Income", "Revenue", "Non-Operating Revenue"),
    acct("5000", "Cost of Goods Sold", "Expense", "COGS"),
    acct("5100", "Salaries and Wages", "Expense", "Operating Expense"),
    acct("5200", "Rent Expense", "Expense", "Operating Expense"),
    acct("5300", "Utilities Expense", "Expense", "Operating Expense"),
    acct("5400", "Marketing Expense", "Expense", "Operating Expense"),
    acct("5500", "IT Expense", "Expense", "Operating Expense"),
    acct("5600", "Travel Expense", "Expense", "Operating Expense"),
    acct("5650", "Bad Debt Expense", "Expense", "Operating Expense"),
    acct("5700", "Depreciation Expense", "Expense", "Non-Cash Expense"),
    acct("5800", "Professional Fees", "Expense", "Operating Expense"),
    acct("5900", "Interest Expense", "Expense", "Finance Cost"),
    acct("6000", "Input GST", "Expense", "Tax"),
]

cost_centers = [
    {"cost_center_code": "CC001", "cost_center_name": "Engineering", "department": "Technology", "budget_annual": 50000000.0},
    {"cost_center_code": "CC002", "cost_center_name": "Sales", "department": "Revenue", "budget_annual": 30000000.0},
    {"cost_center_code": "CC003", "cost_center_name": "Marketing", "department": "Revenue", "budget_annual": 15000000.0},
    {"cost_center_code": "CC004", "cost_center_name": "Finance", "department": "G&A", "budget_annual": 10000000.0},
    {"cost_center_code": "CC005", "cost_center_name": "HR", "department": "G&A", "budget_annual": 8000000.0},
    {"cost_center_code": "CC006", "cost_center_name": "Operations", "department": "Operations", "budget_annual": 25000000.0},
    {"cost_center_code": "CC007", "cost_center_name": "Legal", "department": "G&A", "budget_annual": 5000000.0},
    {"cost_center_code": "CC008", "cost_center_name": "Customer Success", "department": "Revenue", "budget_annual": 12000000.0},
]
for rec in cost_centers:
    rec["_ingested_at"] = INGESTED_AT
cost_center_codes = [cc["cost_center_code"] for cc in cost_centers]

# COMMAND ----------

# MAGIC %md ### P2P: Purchase Orders and Goods Receipts

# COMMAND ----------

vendor_ids = [v["vendor_id"] for v in vendors]
account_codes_expense = ["5000", "5100", "5200", "5300", "5400", "5500", "5600", "5800"]
po_statuses = ["APPROVED", "PARTIALLY_RECEIVED", "FULLY_RECEIVED", "CANCELLED", "PENDING_APPROVAL"]
po_types = ["STANDARD", "BLANKET", "SERVICE", "EMERGENCY"]

po_headers, po_lines = [], []
for i in range(1, PO_COUNT + 1):
    po_date = random_date(400, 10)
    vendor_id = random.choice(vendor_ids)
    po_id = f"PO{i:05d}"
    status = random.choices(po_statuses, weights=[40, 20, 25, 5, 10])[0]
    total_amount = 0.0
    for j in range(1, random.randint(1, 8) + 1):
        unit_price = round(random.uniform(500, 150000), 2)
        qty = random.randint(1, 50)
        line_amount = round(unit_price * qty, 2)
        gst_rate = random.choice([0, 5, 12, 18, 28])
        gst_amount = round(line_amount * gst_rate / 100, 2)
        total_line = round(line_amount + gst_amount, 2)
        total_amount += total_line
        po_lines.append({
            "po_id": po_id, "line_number": j,
            "item_description": fake.catch_phrase(),
            "item_code": f"ITEM{random.randint(1000, 9999)}",
            "quantity": float(qty),
            "unit_of_measure": random.choice(["EA", "KG", "LTR", "MTR", "BOX", "HRS"]),
            "unit_price": unit_price, "line_amount": line_amount,
            "gst_rate": float(gst_rate), "gst_amount": gst_amount, "total_line_amount": total_line,
            "account_code": random.choice(account_codes_expense),
            "cost_center": random.choice(cost_center_codes),
            "_ingested_at": INGESTED_AT, "_source_system": "ERP_SAP"
        })
    company_code = random.choices(["CC_INDIA", "CC_UK"], weights=[80, 20])[0]
    po_headers.append({
        "po_id": po_id,
        "po_number": f"PO-{po_date.year}-{i:05d}",
        "vendor_id": vendor_id,
        "po_date": str(po_date),
        "delivery_date": str(po_date + timedelta(days=random.randint(7, 60))),
        "po_type": random.choice(po_types),
        "status": status,
        "total_amount": round(total_amount, 2),
        "currency": "INR",
        "requestor": fake.name(),
        "approver": fake.name(),
        "approved_date": str(po_date + timedelta(days=random.randint(1, 3))) if status != "PENDING_APPROVAL" else "",
        "company_code": company_code,
        "legal_entity": "MERIDIAN-UK" if company_code == "CC_UK" else "MERIDIAN-IN",
        "_ingested_at": INGESTED_AT, "_source_system": "ERP_SAP"
    })
po_by_id = {p["po_id"]: p for p in po_headers}
po_expense_account = {}
for ln in po_lines:
    po_expense_account.setdefault(ln["po_id"], (ln["account_code"], ln["cost_center"]))

received_pos = [p for p in po_headers if p["status"] in ["PARTIALLY_RECEIVED", "FULLY_RECEIVED"]]
grns = []
for i, po in enumerate(received_pos[:GRN_COUNT], 1):
    grn_date = cap(datetime.strptime(po["po_date"], "%Y-%m-%d").date() + timedelta(days=random.randint(3, 30)))
    receipt_qty_pct = random.uniform(0.5, 1.0) if po["status"] == "PARTIALLY_RECEIVED" else 1.0
    grns.append({
        "grn_id": f"GRN{i:05d}",
        "grn_number": f"GRN-{grn_date.year}-{i:05d}",
        "po_id": po["po_id"],
        "vendor_id": po["vendor_id"],
        "grn_date": str(grn_date),
        "received_by": fake.name(),
        "warehouse_location": random.choice(["WH-MUMBAI-01", "WH-DELHI-01", "WH-BANGALORE-01", "WH-CHENNAI-01"]),
        "status": random.choice(["ACCEPTED", "PARTIALLY_ACCEPTED", "REJECTED"]),
        "received_qty_percentage": round(receipt_qty_pct * 100, 1),
        "received_amount": round(po["total_amount"] * receipt_qty_pct, 2),
        "quality_check_status": random.choices(["PASSED", "FAILED", "PENDING"], weights=[85, 5, 10])[0],
        "remarks": random.choice(["", "", "", "Partial delivery", "Item damaged", "Wrong quantity"]),
        "_ingested_at": INGESTED_AT, "_source_system": "ERP_SAP"
    })

# COMMAND ----------

# MAGIC %md ### P2P: Vendor invoices (age-driven status, coherent GSTIN, re-submitted duplicates) and payments

# COMMAND ----------

def ap_status(days_old: int) -> str:
    if days_old > 90:
        return random.choices(["PAID", "REJECTED", "APPROVED", "PENDING"], weights=[86, 5, 6, 3])[0]
    if days_old > 30:
        return random.choices(["PAID", "APPROVED", "PENDING", "UNDER_REVIEW", "REJECTED"], weights=[50, 25, 10, 10, 5])[0]
    return random.choices(["PENDING", "APPROVED", "UNDER_REVIEW", "PAID", "REJECTED"], weights=[40, 30, 20, 5, 5])[0]

matched_po_ids = [p["po_id"] for p in po_headers if p["status"] not in ["PENDING_APPROVAL", "CANCELLED"]]
p2p_invoices = []
for i in range(1, INVOICE_COUNT + 1):
    po_id = random.choice(matched_po_ids) if random.random() < 0.85 else None
    if po_id:
        po = po_by_id[po_id]
        vendor_id = po["vendor_id"]
        legal_entity = po["legal_entity"]
        # About 20% of PO-backed invoices deviate from the PO beyond the 5% tolerance
        amount_factor = random.choice([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.05, 0.95, 1.10])
        invoice_amount = round(po["total_amount"] * amount_factor, 2)
        invoice_date_base = datetime.strptime(po["po_date"], "%Y-%m-%d").date()
    else:
        vendor_id = random.choice(vendor_ids)
        legal_entity = pick_entity()
        invoice_amount = round(random.uniform(10000, 5000000), 2)
        invoice_date_base = random_date(300, 5)
    vendor = vendor_by_id[vendor_id]
    invoice_date = cap(invoice_date_base + timedelta(days=random.randint(5, 45)))
    tax_amount = round(invoice_amount * 0.18, 2)
    due_days = int(vendor["payment_terms"].replace("NET", ""))
    # GSTIN printed on the invoice is the vendor-master GSTIN; ~2% of invoices arrive without it
    gstin_on_invoice = "" if random.random() < 0.02 else vendor["gstin"]
    p2p_invoices.append({
        "invoice_id": f"INV{i:06d}",
        "invoice_number": f"VINV-{invoice_date.year}-{10000 + i}",
        "vendor_id": vendor_id,
        "po_id": po_id or "",
        "invoice_date": str(invoice_date),
        "due_date": str(invoice_date + timedelta(days=due_days)),
        "invoice_amount": invoice_amount,
        "tax_amount": tax_amount,
        "tax_rate": 18.0,
        "total_amount": round(invoice_amount + tax_amount, 2),
        "currency": "INR",
        "payment_terms": vendor["payment_terms"],
        "status": ap_status(age(invoice_date)),
        "description": fake.bs(),
        "bank_account": vendor["bank_account"],
        "gstin_vendor": gstin_on_invoice,
        "hsn_sac_code": f"{random.randint(1000, 9999)}",
        "tds_applicable": random.choice([True, False]),
        "tds_rate": random.choice([0.0, 1.0, 2.0, 10.0]) if random.random() < 0.3 else 0.0,
        "legal_entity": legal_entity,
        "_ingested_at": INGESTED_AT, "_source_system": "ERP_SAP"
    })
genuine_invoices = list(p2p_invoices)

# ~5% re-submitted duplicates: same vendor + invoice number + amount, new document id, still PENDING.
# The pipeline detects them by (vendor_id, invoice_number); they are never posted to the GL.
duplicate_ids = random.sample(range(900000, 999999), int(INVOICE_COUNT * 0.05))
for src, dup_num in zip(random.sample(genuine_invoices, len(duplicate_ids)), duplicate_ids):
    dup = dict(src)
    dup["invoice_id"] = f"INV{dup_num:06d}"
    dup["status"] = "PENDING"
    p2p_invoices.append(dup)

payment_methods = ["NEFT", "RTGS", "IMPS", "CHEQUE", "WIRE"]
p2p_payments = []
for inv in [x for x in genuine_invoices if x["status"] == "PAID"]:
    inv_date = datetime.strptime(inv["invoice_date"], "%Y-%m-%d").date()
    p2p_payments.append({
        "payment_id": f"PAY{len(p2p_payments) + 1:06d}",
        "invoice_id": inv["invoice_id"],
        "vendor_id": inv["vendor_id"],
        "payment_date": str(cap(inv_date + timedelta(days=random.randint(15, 60)))),
        "payment_amount": inv["total_amount"],
        "currency": "INR",
        "payment_method": random.choice(payment_methods),
        "reference_number": f"REF{random.randint(10000000, 99999999)}",
        "bank_account": inv["bank_account"],
        "status": random.choices(["COMPLETED", "FAILED", "PENDING"], weights=[95, 3, 2])[0],
        "_ingested_at": INGESTED_AT, "_source_system": "ERP_SAP"
    })

# COMMAND ----------

# MAGIC %md ### O2C: Sales orders, customer invoices (age-driven status) and receipts

# COMMAND ----------

customer_ids = [c["customer_id"] for c in customers]
so_statuses = ["CONFIRMED", "SHIPPED", "DELIVERED", "INVOICED", "CANCELLED"]
product_catalog = [
    {"product_code": "PROD001", "product_name": "Data Platform License", "category": "Software", "list_price": 500000.0},
    {"product_code": "PROD002", "product_name": "Analytics Suite", "category": "Software", "list_price": 250000.0},
    {"product_code": "PROD003", "product_name": "Implementation Services", "category": "Services", "list_price": 150000.0},
    {"product_code": "PROD004", "product_name": "Training Package", "category": "Services", "list_price": 80000.0},
    {"product_code": "PROD005", "product_name": "Support Contract Annual", "category": "Support", "list_price": 120000.0},
    {"product_code": "PROD006", "product_name": "Cloud Storage TB", "category": "Infrastructure", "list_price": 5000.0},
    {"product_code": "PROD007", "product_name": "API Gateway License", "category": "Software", "list_price": 180000.0},
    {"product_code": "PROD008", "product_name": "Security Module", "category": "Software", "list_price": 95000.0},
]

sales_orders, so_lines_all = [], []
for i in range(1, SO_COUNT + 1):
    so_date = random_date(500, 5)
    customer_id = random.choice(customer_ids)
    status = random.choices(so_statuses, weights=[15, 10, 20, 45, 10])[0]
    products = random.sample(product_catalog, random.randint(1, 5))
    so_id = f"SO{i:05d}"
    total_amount, max_discount = 0.0, 0
    for j, prod in enumerate(products, 1):
        qty = random.randint(1, 20)
        discount_pct = random.choice([0, 5, 10, 15, 20])
        max_discount = max(max_discount, discount_pct)
        unit_price = prod["list_price"] * (1 - discount_pct / 100)
        line_amount = round(unit_price * qty, 2)
        gst_amount = round(line_amount * 0.18, 2)
        total_line = round(line_amount + gst_amount, 2)
        total_amount += total_line
        so_lines_all.append({
            "so_id": so_id, "line_number": j,
            "product_code": prod["product_code"], "product_name": prod["product_name"],
            "category": prod["category"], "quantity": float(qty),
            "list_price": prod["list_price"], "discount_percentage": float(discount_pct),
            "unit_price": round(unit_price, 2), "line_amount": line_amount,
            "gst_rate": 18.0, "gst_amount": gst_amount, "total_line_amount": total_line,
            "_ingested_at": INGESTED_AT, "_source_system": "CRM_SALESFORCE"
        })
    expected_delivery = so_date + timedelta(days=random.randint(7, 45))
    sales_orders.append({
        "so_id": so_id,
        "so_number": f"SO-{so_date.year}-{i:05d}",
        "customer_id": customer_id,
        "so_date": str(so_date),
        "expected_delivery_date": str(expected_delivery),
        "actual_delivery_date": str(cap(expected_delivery + timedelta(days=random.randint(-5, 15)))) if status in ["DELIVERED", "INVOICED"] else "",
        "status": status,
        "total_amount": round(total_amount, 2),
        "currency": "INR",
        "sales_rep": fake.name(),
        "region": random.choice(["North", "South", "East", "West", "Central"]),
        "discount_approved_by": fake.name() if max_discount > 10 else "",
        "_ingested_at": INGESTED_AT, "_source_system": "CRM_SALESFORCE"
    })


def ar_status(days_old: int) -> str:
    """Open probability falls with age, which yields average days outstanding of roughly 40-75."""
    if days_old <= 30:
        return random.choices(["OUTSTANDING", "PARTIAL_PAID", "PAID"], weights=[85, 5, 10])[0]
    if days_old <= 60:
        return random.choices(["OUTSTANDING", "OVERDUE", "PARTIAL_PAID", "PAID"], weights=[25, 25, 5, 45])[0]
    if days_old <= 90:
        return random.choices(["OVERDUE", "PARTIAL_PAID", "PAID"], weights=[20, 5, 75])[0]
    if days_old <= 150:
        return random.choices(["OVERDUE", "PAID"], weights=[8, 92])[0]
    return random.choices(["OVERDUE", "WRITTEN_OFF", "PAID"], weights=[1, 1, 98])[0]

o2c_invoices = []
for i, so in enumerate([s for s in sales_orders if s["status"] == "INVOICED"], 1):
    so_date = datetime.strptime(so["so_date"], "%Y-%m-%d").date()
    inv_date = cap(so_date + timedelta(days=random.randint(1, 10)))
    amount = so["total_amount"]
    tax = round(amount * 0.18 / 1.18, 2)
    o2c_invoices.append({
        "o2c_invoice_id": f"CINV{i:06d}",
        "invoice_number": f"SINV-{inv_date.year}-{10000 + i}",
        "so_id": so["so_id"],
        "customer_id": so["customer_id"],
        "invoice_date": str(inv_date),
        "due_date": str(inv_date + timedelta(days=random.choice([30, 45, 60]))),
        "invoice_amount": round(amount - tax, 2),
        "tax_amount": tax,
        "total_amount": amount,
        "currency": "INR",
        "payment_terms": random.choice(payment_terms_options),
        "status": ar_status(age(inv_date)),
        "legal_entity": customer_by_id[so["customer_id"]]["legal_entity"],
        "_ingested_at": INGESTED_AT, "_source_system": "ERP_SAP"
    })

o2c_payments = []
for inv in [x for x in o2c_invoices if x["status"] in ["PAID", "PARTIAL_PAID"]]:
    inv_date = datetime.strptime(inv["invoice_date"], "%Y-%m-%d").date()
    pct_paid = 1.0 if inv["status"] == "PAID" else random.uniform(0.3, 0.9)
    o2c_payments.append({
        "receipt_id": f"RCP{len(o2c_payments) + 1:06d}",
        "o2c_invoice_id": inv["o2c_invoice_id"],
        "customer_id": inv["customer_id"],
        "payment_date": str(cap(inv_date + timedelta(days=random.randint(10, 50)))),
        "payment_amount": round(inv["total_amount"] * pct_paid, 2),
        "currency": "INR",
        "payment_method": random.choice(["NEFT", "RTGS", "CHEQUE", "ONLINE"]),
        "reference_number": f"REF{random.randint(10000000,99999999)}",
        "status": "CLEARED",
        "_ingested_at": INGESTED_AT, "_source_system": "ERP_SAP"
    })

# COMMAND ----------

# MAGIC %md ### R2R: General ledger derived from the sub-ledgers, plus manual journals
# MAGIC
# MAGIC | Source document | Debit | Credit |
# MAGIC |---|---|---|
# MAGIC | AR invoice | 1100 AR (gross) | 4000/4100 Revenue (net), 2600 GST payable (tax) |
# MAGIC | Customer receipt | 1000 Cash | 1100 AR |
# MAGIC | AR write-off | 5650 Bad debt | 1100 AR |
# MAGIC | AP invoice | 5xxx Expense (net), 6000 Input GST (tax) | 2000 AP (gross) |
# MAGIC | Vendor payment (completed) | 2000 AP | 1000 Cash |
# MAGIC | Manual journals | various | various (never 1100 or 2000) |

# COMMAND ----------

journal_entries, je_lines = [], []

def post(je_date: date, je_type: str, lines: list[tuple], description: str, source_module: str,
         source_document_id: str = "", status: str = "POSTED", cost_center: str = None):
    """lines: [(account_code, debit, credit)]. Header totals are taken from the lines."""
    je_id = f"JE{len(journal_entries) + 1:06d}"
    cc = cost_center or random.choice(cost_center_codes)
    total_dr = round(sum(l[1] for l in lines), 2)
    total_cr = round(sum(l[2] for l in lines), 2)
    journal_entries.append({
        "je_id": je_id,
        "je_number": f"JE-{je_date.year}-{len(journal_entries) + 1:06d}",
        "je_date": str(je_date),
        "je_type": je_type,
        "description": description,
        "period": f"{je_date.year}-{je_date.month:02d}",
        "fiscal_year": je_date.year,
        "posted_by": "SYSTEM" if source_module != "GL" else fake.name(),
        "approved_by": "SYSTEM" if source_module != "GL" else fake.name(),
        "status": status,
        "total_debit": total_dr,
        "total_credit": total_cr,
        "source_module": source_module,
        "source_document_id": source_document_id,
        "_ingested_at": INGESTED_AT, "_source_system": "ERP_SAP"
    })
    for n, (code, dr, cr) in enumerate(lines, 1):
        je_lines.append({
            "je_id": je_id, "line_number": n, "account_code": code, "cost_center": cc,
            "debit_amount": round(dr, 2), "credit_amount": round(cr, 2),
            "description": description, "_ingested_at": INGESTED_AT
        })
    return je_id

# Reconciling items: sub-ledger documents whose GL journal is still DRAFT (not yet posted).
open_ar = sorted([x for x in o2c_invoices if x["status"] == "OUTSTANDING"], key=lambda x: x["invoice_date"], reverse=True)
open_ap = sorted([x for x in genuine_invoices if x["status"] == "APPROVED"], key=lambda x: x["invoice_date"], reverse=True)
ar_seed_ids = {x["o2c_invoice_id"] for x in open_ar[:3]}
ap_seed_ids = {x["invoice_id"] for x in open_ap[:1]}
recon_seed_items = []

# Opening capital so cash is not negative
first_day = TODAY - timedelta(days=760)
post(first_day, "MANUAL", [("1000", 2_500_000_000.0, 0.0), ("3000", 0.0, 2_500_000_000.0)],
     "Opening share capital", "GL")

for inv in o2c_invoices:
    d = datetime.strptime(inv["invoice_date"], "%Y-%m-%d").date()
    seeded = inv["o2c_invoice_id"] in ar_seed_ids
    rev_acct = random.choice(["4000", "4100"])
    je_id = post(d, "SYSTEM_AUTO",
                 [("1100", inv["total_amount"], 0.0), (rev_acct, 0.0, inv["invoice_amount"]), ("2600", 0.0, inv["tax_amount"])],
                 f"AR invoice {inv['invoice_number']}", "AR", inv["o2c_invoice_id"],
                 status="DRAFT" if seeded else "POSTED")
    if seeded:
        recon_seed_items.append({"account_code": "1100", "document_id": inv["o2c_invoice_id"],
                                 "document_type": "AR_INVOICE", "amount": inv["total_amount"],
                                 "reason": "Invoice posted in the AR sub-ledger; GL journal still in DRAFT awaiting approval",
                                 "gl_je_id": je_id, "gl_je_status": "DRAFT"})
    if inv["status"] == "WRITTEN_OFF":
        post(cap(d + timedelta(days=150)), "MANUAL", [("5650", inv["total_amount"], 0.0), ("1100", 0.0, inv["total_amount"])],
             f"Write-off {inv['invoice_number']}", "AR", inv["o2c_invoice_id"])

for rcp in o2c_payments:
    post(datetime.strptime(rcp["payment_date"], "%Y-%m-%d").date(), "SYSTEM_AUTO",
         [("1000", rcp["payment_amount"], 0.0), ("1100", 0.0, rcp["payment_amount"])],
         f"Customer receipt {rcp['receipt_id']}", "AR", rcp["receipt_id"])

for inv in genuine_invoices:
    if inv["status"] == "REJECTED":
        continue
    d = datetime.strptime(inv["invoice_date"], "%Y-%m-%d").date()
    exp_acct, cc = po_expense_account.get(inv["po_id"], ("5800", None))
    seeded = inv["invoice_id"] in ap_seed_ids
    je_id = post(d, "SYSTEM_AUTO",
                 [(exp_acct, inv["invoice_amount"], 0.0), ("6000", inv["tax_amount"], 0.0), ("2000", 0.0, inv["total_amount"])],
                 f"AP invoice {inv['invoice_number']}", "AP", inv["invoice_id"],
                 status="DRAFT" if seeded else "POSTED", cost_center=cc)
    if seeded:
        recon_seed_items.append({"account_code": "2000", "document_id": inv["invoice_id"],
                                 "document_type": "AP_INVOICE", "amount": inv["total_amount"],
                                 "reason": "Invoice approved in the AP sub-ledger; GL journal still in DRAFT awaiting approval",
                                 "gl_je_id": je_id, "gl_je_status": "DRAFT"})

for pay in [p for p in p2p_payments if p["status"] == "COMPLETED"]:
    post(datetime.strptime(pay["payment_date"], "%Y-%m-%d").date(), "SYSTEM_AUTO",
         [("2000", pay["payment_amount"], 0.0), ("1000", 0.0, pay["payment_amount"])],
         f"Vendor payment {pay['payment_id']}", "AP", pay["payment_id"])

# Manual journals: balanced, realistic pairs, never on the control accounts
manual_templates = [
    ("PAYROLL", "5100", "1000"), ("DEPRECIATION", "5700", "1600"),
    ("ACCRUAL", "5200", "2100"), ("ACCRUAL", "5300", "2100"), ("ACCRUAL", "5800", "2100"),
    ("REVERSAL", "2100", "5800"), ("MANUAL", "5400", "1000"), ("MANUAL", "5500", "1000"),
    ("MANUAL", "5600", "1000"), ("MANUAL", "1300", "1000"), ("SYSTEM_AUTO", "5900", "1000"),
    ("SYSTEM_AUTO", "1000", "2200"), ("MANUAL", "1500", "1000"), ("MANUAL", "1000", "4200"),
]
for i in range(600):
    je_type, dr, cr = random.choice(manual_templates)
    amount = round(random.uniform(10000, 5000000), 2)
    status = random.choices(["POSTED", "DRAFT", "REVERSED"], weights=[88, 8, 4])[0]
    post(random_date(365, 0), je_type, [(dr, amount, 0.0), (cr, 0.0, amount)], fake.bs(), "GL", status=status)

# A handful of deliberately unbalanced manual journals: quarantined by the pipeline, never in the GL
for i in range(5):
    amount = round(random.uniform(50000, 900000), 2)
    post(random_date(120, 0), "MANUAL", [("5800", amount, 0.0), ("2100", 0.0, round(amount * 0.97, 2))],
         "Manual accrual keyed with a transposition error", "GL")

print(f"Journals: {len(journal_entries)}  lines: {len(je_lines)}  reconciling items: {len(recon_seed_items)}")

# COMMAND ----------

# MAGIC %md ## Land every entity as raw CSV

# COMMAND ----------

write_csv("vendors", vendors)
write_csv("customers", customers)
write_csv("chart_of_accounts", chart_of_accounts)
write_csv("cost_centers", cost_centers)
write_csv("po_header", po_headers)
write_csv("po_line", po_lines)
write_csv("grn", grns)
write_csv("p2p_invoices", p2p_invoices)
write_csv("p2p_payments", p2p_payments)
write_csv("sales_orders", sales_orders)
write_csv("so_lines", so_lines_all)
write_csv("o2c_invoices", o2c_invoices)
write_csv("o2c_payments", o2c_payments)
write_csv("journal_entries", journal_entries)
write_csv("je_lines", je_lines)
write_csv("recon_seed_items", recon_seed_items)

# COMMAND ----------

import json
gstin_match = sum(1 for x in genuine_invoices if x["gstin_vendor"] and x["gstin_vendor"] == vendor_by_id[x["vendor_id"]]["gstin"])
gstin_expected = sum(1 for x in genuine_invoices if vendor_by_id[x["vendor_id"]]["gstin"])
summary = {
    "raw_csv_path": RAW_CSV,
    "rows": written,
    "duplicate_invoices": len(duplicate_ids),
    "gstin_match_pct": round(100.0 * gstin_match / max(gstin_expected, 1), 1),
    "reconciling_items": len(recon_seed_items),
}
print(json.dumps(summary, indent=2))
dbutils.notebook.exit(json.dumps(summary))
