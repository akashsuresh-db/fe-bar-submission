"""SSE stream generators for the finance event feeds.

The feeds are a REPLAY of governed Gold rows in posting-date order (oldest of the
most recent N first) — not live ERP events. Every flag shown (match status,
release block, auto-matched receipt) comes from the data; `random` is used only
for cosmetic pacing between events.
"""
import asyncio
import json
import random  # cosmetic timing jitter only
from typing import AsyncGenerator
from backend.currency import usd
from backend import db


def _fmt(val) -> str | int | float | None:
    """Format DB values for JSON serialization."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    return str(val)


def _serialize_row(row: dict) -> dict:
    """Convert all values in a row to JSON-safe types."""
    return {k: _fmt(v) for k, v in row.items()}


# ─── Exception detection logic ────────────────────────────────

def _is_true(v) -> bool:
    return str(v).lower() == "true" or v is True


def _detect_p2p_exceptions(inv: dict) -> list[dict]:
    """Detect AP exceptions for an invoice."""
    exceptions = []
    ms = str(inv.get("match_status", ""))
    if _is_true(inv.get("release_blocked")):
        erp = float(inv.get("invoice_total_inr", 0) or 0)
        pdf = inv.get("ai_extracted_amount")
        detail = f" (PDF {usd(float(pdf), exact=True)} vs ERP {usd(erp, exact=True)})" if pdf is not None else ""
        exceptions.append({
            "type": "quarantine",
            "rule": "release_blocked",
            "severity": "critical",
            "reason": f"Blocked: PDF ≠ ERP — {inv.get('block_reason') or 'AI extraction disagrees with the ERP record'}{detail}",
            "resolution": "Payment release blocked. Confirm the invoice with the vendor before releasing.",
        })
    if ms == "AMOUNT_MISMATCH":
        exceptions.append({
            "type": "quarantine",
            "rule": "amount_match",
            "severity": "high",
            "reason": "Invoice amount does not match PO amount (variance exceeds 5% threshold)",
            "resolution": "Compare invoice line items against PO {po}. Contact vendor if discrepancy confirmed.".format(
                po=inv.get("po_id", "N/A")
            ),
        })
    if ms == "NO_PO_REFERENCE":
        exceptions.append({
            "type": "quarantine",
            "rule": "has_po_ref",
            "severity": "high",
            "reason": "Invoice has no Purchase Order reference — cannot perform 3-way match",
            "resolution": "Route to AP supervisor for manual PO assignment or rejection.",
        })
    if str(inv.get("is_overdue", "")).lower() == "true":
        age = inv.get("aging_days", 0)
        if age and int(age) > 60:
            exceptions.append({
                "type": "exception",
                "rule": "overdue_critical",
                "severity": "critical",
                "reason": f"Invoice is {age} days overdue — approaching write-off threshold",
                "resolution": "Escalate to AP Supervisor for immediate payment authorization.",
            })
    if not inv.get("gstin_vendor"):
        exceptions.append({
            "type": "exception",
            "rule": "missing_gstin",
            "severity": "medium",
            "reason": "Vendor GSTIN is missing — GST input credit cannot be claimed",
            "resolution": "Request updated GST registration from vendor before processing.",
        })
    return exceptions


def _detect_o2c_exceptions(col: dict) -> list[dict]:
    """Detect AR exceptions for a collection record."""
    exceptions = []
    status = str(col.get("invoice_status", ""))
    outstanding = float(col.get("balance_outstanding", 0) or 0)
    days_overdue = int(col.get("days_overdue", 0) or 0)

    if status == "WRITTEN_OFF":
        exceptions.append({
            "type": "quarantine",
            "rule": "written_off",
            "severity": "critical",
            "reason": f"Invoice written off — {usd(outstanding)} unrecoverable",
            "resolution": "Review with Credit Manager for bad debt provisioning.",
        })
    elif days_overdue > 90:
        exceptions.append({
            "type": "quarantine",
            "rule": "critical_overdue",
            "severity": "critical",
            "reason": f"Invoice is {days_overdue} days overdue — {usd(outstanding)} at risk",
            "resolution": "Escalate to Credit Manager. Consider legal collection action.",
        })
    elif days_overdue > 60:
        exceptions.append({
            "type": "exception",
            "rule": "aging_concern",
            "severity": "high",
            "reason": f"Invoice {days_overdue} days overdue — moving into concern bucket",
            "resolution": "Priority collection call required. Update PTP commitment.",
        })
    if outstanding > 5_000_000:
        exceptions.append({
            "type": "exception",
            "rule": "high_value_outstanding",
            "severity": "high",
            "reason": f"High-value outstanding: {usd(outstanding)}",
            "resolution": "Assign dedicated collection follow-up.",
        })
    return exceptions


def _detect_r2r_exceptions(je: dict, je_lines: list[dict]) -> list[dict]:
    """Detect GL exceptions for a journal entry."""
    exceptions = []
    total_debit = sum(float(l.get("debit_inr", 0) or 0) for l in je_lines)
    total_credit = sum(float(l.get("credit_inr", 0) or 0) for l in je_lines)
    diff = abs(total_debit - total_credit)

    if diff > 0.01:
        exceptions.append({
            "type": "quarantine",
            "rule": "je_balanced",
            "severity": "critical",
            "reason": f"Journal entry is UNBALANCED — Debit: {usd(total_debit, exact=True)}, Credit: {usd(total_credit, exact=True)}, Difference: {usd(diff, exact=True)}",
            "resolution": f"Review entry posted by {je.get('posted_by', 'Unknown')}. Correct the imbalance before period close.",
        })
    if total_debit > 5_000_000:
        exceptions.append({
            "type": "exception",
            "rule": "high_value_je",
            "severity": "medium",
            "reason": f"High-value journal entry: {usd(total_debit)} — requires controller approval",
            "resolution": "Route to Vikram (Financial Controller) for sign-off.",
        })
    return exceptions


# ─── SSE Generators ────────────────────────────────────────────

def _unavailable(e: Exception) -> str:
    return json.dumps({"type": "error", "data": {
        "error": "warehouse_unavailable" if isinstance(e, db.WarehouseUnavailable) else "query_error",
        "message": str(e)[:300]}})


async def stream_p2p() -> AsyncGenerator[str, None]:
    """Replay the latest 100 AP invoices in invoice-date order."""
    try:
        invoices = await asyncio.to_thread(db.get_invoices, 100)
    except Exception as e:
        yield _unavailable(e)
        return
    invoices = list(reversed(invoices))  # oldest → newest

    # Morning greeting
    total = len(invoices)
    exceptions_count = sum(1 for i in invoices if i.get("exception_type") or _is_true(i.get("release_blocked")))
    overdue_count = sum(1 for i in invoices if str(i.get("is_overdue", "")).lower() == "true")
    total_amount = sum(float(i.get("invoice_total_inr", 0) or 0) for i in invoices)

    yield json.dumps({
        "type": "greeting",
        "data": {
            "persona": "",
            "role": "AP Operations Lead",
            "message": f"{total} invoices queued today.\n  {exceptions_count} require your attention: exceptions & mismatches\n  {overdue_count} overdue invoices flagged\nTotal value in queue: {usd(total_amount)}",
        }
    })
    await asyncio.sleep(0.3)

    processed = 0
    matched_count = 0
    exception_count = 0

    for inv in invoices:
        row = _serialize_row(inv)

        # Simulate match status animation
        ms = inv.get("match_status", "")
        if ms == "THREE_WAY_MATCHED" and not _is_true(inv.get("release_blocked")):
            # Show running then matched
            row["_anim_status"] = "running"
            yield json.dumps({"type": "invoice_processing", "data": row})
            await asyncio.sleep(random.uniform(0.3, 0.8))
            row["_anim_status"] = "matched"
            matched_count += 1

        yield json.dumps({"type": "invoice", "data": row})
        processed += 1

        # Check for exceptions
        excs = _detect_p2p_exceptions(inv)
        for exc in excs:
            exception_count += 1
            exc_data = {**exc, "invoice_id": inv.get("invoice_id"), "vendor_name": inv.get("vendor_name"),
                        "amount": float(inv.get("invoice_total_inr", 0) or 0), "invoice_number": inv.get("invoice_number")}
            yield json.dumps({"type": exc["type"], "data": exc_data})
            await asyncio.sleep(0.2)

        # Progress update every 10 invoices
        if processed % 10 == 0:
            yield json.dumps({
                "type": "progress",
                "data": {"processed": processed, "total": total, "matched": matched_count, "exceptions": exception_count}
            })

        await asyncio.sleep(random.uniform(0.4, 1.2))

    # End of day summary
    yield json.dumps({
        "type": "summary",
        "data": {
            "processed": processed,
            "matched": matched_count,
            "exceptions": exception_count,
            "touchless_rate": round(matched_count / max(processed, 1) * 100, 1),
            "message": f"Today, Databricks handled {matched_count} invoices automatically through 3-way matching — what used to take 6.5 hours. Your team focused on: {exception_count} exception reviews, vendor escalations, and judgment calls."
        }
    })


async def stream_o2c() -> AsyncGenerator[str, None]:
    """Replay the latest 100 customer invoices in invoice-date order."""
    try:
        collections = await asyncio.to_thread(db.get_collections, 100)
    except Exception as e:
        yield _unavailable(e)
        return
    collections = list(reversed(collections))  # oldest → newest

    total_outstanding = sum(float(c.get("balance_outstanding", 0) or 0) for c in collections)
    overdue = [c for c in collections if int(c.get("days_overdue", 0) or 0) > 0]

    # Bucket breakdown
    buckets = {}
    for c in collections:
        b = c.get("aging_bucket", "Unknown")
        buckets[b] = buckets.get(b, 0) + float(c.get("balance_outstanding", 0) or 0)

    yield json.dumps({
        "type": "greeting",
        "data": {
            "persona": "",
            "role": "Collections Specialist",
            "message": f"AR portfolio: {usd(total_outstanding)} outstanding\n  {len(overdue)} overdue accounts requiring action\n  Priority calls today: {min(len(overdue), 12)} accounts",
            "buckets": {k: round(v, 0) for k, v in buckets.items()},
        }
    })
    await asyncio.sleep(0.3)

    processed = 0
    collected_today = 0
    exceptions_found = 0

    for col in collections:
        row = _serialize_row(col)

        # Simulate payment events
        collected = float(col.get("amount_collected_inr", 0) or 0)
        if collected > 0:
            # auto_matched comes from the data: a receipt for the same invoice and amount exists.
            yield json.dumps({"type": "payment_received", "data": {
                **row, "event": "cash_applied",
                "auto_matched": _is_true(col.get("auto_matched")),
            }})
            collected_today += collected
        else:
            yield json.dumps({"type": "collection", "data": row})

        processed += 1

        # Check exceptions
        excs = _detect_o2c_exceptions(col)
        for exc in excs:
            exceptions_found += 1
            exc_data = {**exc, "invoice_id": col.get("o2c_invoice_id"),
                        "customer_name": col.get("customer_name"),
                        "amount": float(col.get("balance_outstanding", 0) or 0),
                        "invoice_number": col.get("invoice_number")}
            yield json.dumps({"type": exc["type"], "data": exc_data})
            await asyncio.sleep(0.2)

        if processed % 10 == 0:
            yield json.dumps({
                "type": "progress",
                "data": {"processed": processed, "total": len(collections),
                         "collected_today": collected_today, "exceptions": exceptions_found}
            })

        await asyncio.sleep(random.uniform(0.4, 1.2))

    yield json.dumps({
        "type": "summary",
        "data": {
            "processed": processed,
            "collected_today": collected_today,
            "exceptions": exceptions_found,
            "message": f"Today's collection run: {processed} accounts reviewed. {usd(collected_today)} cash applied. {exceptions_found} exceptions flagged for follow-up."
        }
    })


async def stream_r2r() -> AsyncGenerator[str, None]:
    """Replay the latest journal entries in posting-date order."""
    try:
        entries = await asyncio.to_thread(db.get_journal_entries, 200)
    except Exception as e:
        yield _unavailable(e)
        return

    # Group by je_id to process complete journal entries
    je_groups: dict[str, list[dict]] = {}
    for e in entries:
        jid = e["je_id"]
        if jid not in je_groups:
            je_groups[jid] = []
        je_groups[jid].append(e)

    # Oldest → newest by posting date
    je_list = sorted(je_groups.items(), key=lambda kv: (str(kv[1][0].get("je_date", "")), kv[0]))
    periods = sorted({str(e.get("period") or "") for e in entries if e.get("period")})
    close_period = periods[-1] if periods else "current period"

    total_jes = len(je_list)
    # Close checklist items
    checklist = [
        {"task": "Standard recurring JEs posted", "owner": "Sunita", "status": "completed"},
        {"task": "Payroll accrual booked", "owner": "Sunita", "status": "completed"},
        {"task": "Depreciation JE", "owner": "Sunita", "status": "in_progress"},
        {"task": "Prepaid expense amortization", "owner": "Sunita", "status": "pending"},
        {"task": "Revenue recognition adjustments", "owner": "Sunita", "status": "pending"},
        {"task": "Bank reconciliation — Final", "owner": "Sunita", "status": "pending"},
        {"task": "Intercompany eliminations", "owner": "Vikram", "status": "pending"},
        {"task": "Controller review & sign-off", "owner": "Vikram", "status": "pending"},
    ]

    yield json.dumps({
        "type": "greeting",
        "data": {
            "persona": "",
            "role": "GL Accountant",
            "message": f"Month-End Close: {close_period}\n\n{total_jes} journal entries to validate (replay of posted GL lines)\nClose checklist (illustrative): 2 of {len(checklist)} tasks complete",
            "checklist": checklist,
        }
    })
    await asyncio.sleep(0.3)

    posted = 0
    quarantined = 0
    running_debit = 0.0
    running_credit = 0.0

    for je_id, lines in je_list[-60:]:  # Limit to 60 JEs for reasonable stream
        first = lines[0]
        total_debit = sum(float(l.get("debit_inr", 0) or 0) for l in lines)
        total_credit = sum(float(l.get("credit_inr", 0) or 0) for l in lines)
        is_balanced = abs(total_debit - total_credit) < 0.01

        running_debit += total_debit
        running_credit += total_credit

        je_data = {
            "je_id": je_id,
            "je_number": first.get("je_number"),
            "je_date": str(first.get("je_date", "")),
            "je_type": first.get("je_type"),
            "posted_by": first.get("posted_by"),
            "status": first.get("status"),
            "department": first.get("department"),
            "total_debit": total_debit,
            "total_credit": total_credit,
            "is_balanced": is_balanced,
            "line_count": len(lines),
            "lines": [
                {
                    "line": l.get("gl_line_number"),
                    "account_code": l.get("account_code"),
                    "account_name": l.get("account_name"),
                    "debit": float(l.get("debit_inr", 0) or 0),
                    "credit": float(l.get("credit_inr", 0) or 0),
                    "description": l.get("gl_description"),
                }
                for l in lines
            ],
        }

        yield json.dumps({"type": "journal_entry", "data": je_data})
        posted += 1

        # Check for exceptions
        excs = _detect_r2r_exceptions(first, lines)
        for exc in excs:
            if exc["type"] == "quarantine":
                quarantined += 1
            exc_data = {**exc, **je_data}
            yield json.dumps({"type": exc["type"], "data": exc_data})
            await asyncio.sleep(0.2)

        # Trial balance update
        if posted % 5 == 0:
            yield json.dumps({
                "type": "tb_update",
                "data": {
                    "posted": posted,
                    "quarantined": quarantined,
                    "running_debit": running_debit,
                    "running_credit": running_credit,
                    "is_balanced": abs(running_debit - running_credit) < 1.0,
                }
            })

            # Advance checklist
            if posted >= 15 and checklist[2]["status"] == "in_progress":
                checklist[2]["status"] = "completed"
                checklist[3]["status"] = "in_progress"
                yield json.dumps({"type": "checklist_update", "data": {"checklist": checklist}})
            elif posted >= 30 and checklist[3]["status"] == "in_progress":
                checklist[3]["status"] = "completed"
                checklist[4]["status"] = "in_progress"
                yield json.dumps({"type": "checklist_update", "data": {"checklist": checklist}})

        await asyncio.sleep(random.uniform(0.5, 1.5))

    yield json.dumps({
        "type": "summary",
        "data": {
            "posted": posted,
            "quarantined": quarantined,
            "running_debit": running_debit,
            "running_credit": running_credit,
            "is_balanced": abs(running_debit - running_credit) < 1.0,
            "message": f"Journal entry validation complete. {posted} entries posted, {quarantined} quarantined. Trial balance {'BALANCED' if abs(running_debit - running_credit) < 1.0 else 'IMBALANCED — review required'}."
        }
    })
