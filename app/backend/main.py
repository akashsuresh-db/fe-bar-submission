"""Finance Operations App — FastAPI backend."""
import json
import asyncio
import uuid
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from backend import db
from backend.streams import stream_p2p, stream_o2c, stream_r2r
from backend.chat import stream_mas_agent, AGENT_ENDPOINT, select_route
from backend import lakebase
from backend.invoice_pdf import build_invoice_pdf
from backend import escalate
from backend import summary as summary_mod
from backend.config import (
    CATALOG, SCHEMA, DEMO_MODE, GENIE_SPACE_ID, WAREHOUSE_ID,
    set_user_token, reset_user_token, auth_mode,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: probe the warehouse with the app service principal (no request yet).
    # A failure is NOT a switch to demo data: endpoints keep retrying and return a
    # typed 503 until the warehouse answers; the UI shows a banner meanwhile.
    if DEMO_MODE:
        print("DEMO_MODE=true — serving fixture metrics; warehouse queries disabled")
    else:
        try:
            result = await asyncio.wait_for(asyncio.to_thread(db.query, "SELECT 1 as ok"), timeout=120.0)
            print(f"Database connection verified: {result}")
        except asyncio.TimeoutError:
            print("WARNING: warehouse probe timed out at startup (cold start) — will retry per request")
        except Exception as e:
            print(f"WARNING: warehouse probe failed: {e} — will retry per request")
    # Initialize Lakebase schema (also with timeout)
    try:
        await asyncio.wait_for(
            asyncio.to_thread(lakebase.init_schema),
            timeout=20.0,
        )
        print("Lakebase schema initialized successfully")
    except asyncio.TimeoutError:
        print("WARNING: Lakebase init timed out — will use in-memory fallback")
    except Exception as e:
        print(f"WARNING: Lakebase init failed (will use demo mode): {e}")
    yield


app = FastAPI(title="Finance Operations App", lifespan=lifespan)


class OboTokenMiddleware:
    """Pure-ASGI middleware: expose the forwarded user token to backend.config for
    the lifetime of the request (including streamed responses), so warehouse reads
    run on behalf of the user. Pure ASGI (not BaseHTTPMiddleware) keeps the
    contextvar visible inside StreamingResponse generators."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        token = None
        for k, v in scope.get("headers", []):
            if k == b"x-forwarded-access-token":
                token = v.decode()
                break
        ctx = set_user_token(token)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_user_token(ctx)


app.add_middleware(OboTokenMiddleware)


@app.exception_handler(db.WarehouseUnavailable)
async def _warehouse_unavailable(request: Request, exc: db.WarehouseUnavailable):
    return JSONResponse(status_code=503, content={
        "error": "demo_mode" if DEMO_MODE else "warehouse_unavailable",
        "message": "Warehouse starting — data unavailable" if not DEMO_MODE else "Demo mode — no live data",
        "detail": str(exc)[:300],
    })


@app.exception_handler(db.QueryError)
async def _query_error(request: Request, exc: db.QueryError):
    return JSONResponse(status_code=502, content={"error": "query_error", "detail": str(exc)[:500]})

# ─── API Routes ──────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "healthy", "app": "finance-operations"}


@app.get("/api/debug/status")
async def debug_status():
    """Diagnostics: data mode, auth mode, Lakebase, Genie, escalate config."""
    from backend import escalate as _esc
    from backend.chat import MAS_ENDPOINT
    ds = db.data_status()
    return {
        "demo_mode": DEMO_MODE,
        "auth_mode": auth_mode(),
        "db": {
            **ds,
            "catalog": CATALOG,
            "schema": SCHEMA,
        },
        "lakebase": lakebase.get_status(),
        "genie": {
            "configured": bool(GENIE_SPACE_ID),
            "space_id": GENIE_SPACE_ID,
            "mas_endpoint": MAS_ENDPOINT or None,
            "chat_route": select_route(),
        },
        "escalate": {
            "alert_id": _esc._alert_id,
            "dest_id": _esc._dest_id,
            "recipient": _esc.RECIPIENT,
            "sql_cached": bool(_esc._last_sql),
        },
    }


@app.get("/api/data-status")
async def data_status():
    """Lightweight status for the UI banner: is the backend serving live rows?"""
    ds = db.data_status()
    if ds["live"] is not True and not DEMO_MODE:
        # Probe so the banner clears as soon as the warehouse is back.
        try:
            await asyncio.to_thread(db.query, "SELECT 1 AS ok")
        except Exception:
            pass
        ds = db.data_status()
    banner = None
    if DEMO_MODE:
        banner = "Demo data — not connected to the lakehouse"
    elif ds["live"] is not True:
        banner = "Warehouse starting — data unavailable"
    return {**ds, "auth_mode": auth_mode(), "banner": banner}


# ── User Identity ──

@app.get("/api/me")
async def me(request: Request):
    email = request.headers.get("x-forwarded-email", "")
    raw = request.headers.get("x-forwarded-preferred-username", "") or email.split("@")[0]
    # "jane.doe" -> "Jane", "jane.smith" -> "Jane"
    first = raw.replace(".", " ").split()[0].capitalize() if raw else "User"
    return {"name": first, "email": email, "username": raw}


# ── Metrics ──

@app.get("/api/verify-invoice/{invoice_id}")
async def verify_invoice(invoice_id: str):
    """
    Pre-approval credibility check for an invoice. Pulls the ERP record, PO, AI
    extraction, and vendor master in one shot and returns a list of 8 named
    checks each with a status (PASS / WARN / FAIL) and human-readable detail.

    The frontend renders these as a pre-approval panel; the recommendation
    string at the end ("APPROVE" / "HOLD" / "REJECT") drives the badge colour.
    """
    sql = f"""
        WITH i AS (
            SELECT * FROM {CATALOG}.{SCHEMA}.gold_fact_invoices
            WHERE invoice_id = %(invoice_id)s OR invoice_number = %(invoice_id)s
            LIMIT 1
        ),
        x AS (
            SELECT * FROM {CATALOG}.{SCHEMA}.silver_invoice_extractions
            WHERE invoice_id IN (SELECT invoice_id FROM i)
            LIMIT 1
        )
        SELECT
            i.invoice_id, i.invoice_number, i.vendor_id, i.vendor_name,
            i.po_id, i.invoice_amount, i.invoice_total_inr,
            i.gstin_vendor, i.match_status, i.is_overdue, i.aging_days,
            i.data_source, i.pdf_file_path,
            i.release_blocked, i.block_reason, i.ai_extracted_amount,
            p.total_amount AS po_total_amount,
            v.gstin AS vendor_master_gstin,
            v.country AS vendor_country,
            v.state AS vendor_state,
            v.is_active AS vendor_is_active,
            x.extracted_vendor_name, x.extracted_total_amount,
            x.extracted_subtotal, x.extracted_gstin, x.extracted_po_reference
        FROM i
        LEFT JOIN {CATALOG}.{SCHEMA}.silver_po_header  p ON i.po_id     = p.po_id
        LEFT JOIN {CATALOG}.{SCHEMA}.bronze_vendors    v ON i.vendor_id = v.vendor_id
        LEFT JOIN x ON i.invoice_id = x.invoice_id
    """
    rows = await asyncio.to_thread(db.query, sql, {"invoice_id": invoice_id})
    if not rows:
        return JSONResponse({"error": f"invoice {invoice_id} not found"}, status_code=404)

    r = rows[0]
    release_blocked = bool(r.get("release_blocked"))
    inv_amt   = float(r.get("invoice_amount") or 0)
    inv_total = float(r.get("invoice_total_inr") or 0)
    po_total  = float(r.get("po_total_amount") or 0)
    ex_total  = float(r.get("extracted_total_amount") or 0)
    ex_sub    = float(r.get("extracted_subtotal") or 0)

    def _ratio(a, b):
        return abs(a - b) / b if b else 1.0

    erp_vendor = (r.get("vendor_name") or "").strip().lower()
    ex_vendor  = (r.get("extracted_vendor_name") or "").strip().lower()
    erp_gstin  = (r.get("vendor_master_gstin") or r.get("gstin_vendor") or "").strip().upper()
    ex_gstin   = (r.get("extracted_gstin") or "").strip().upper()
    erp_po     = (r.get("po_id") or "").strip()
    ex_po      = (r.get("extracted_po_reference") or "").strip()

    checks = []

    # 1. Invoice total vs PO total (3-way match)
    if po_total > 0:
        v = _ratio(inv_total, po_total)
        if v <= 0.05:
            checks.append({"id":1, "name":"Invoice ↔ PO total", "status":"PASS",
                           "detail":f"₹{inv_total/1e7:.2f} Cr vs ₹{po_total/1e7:.2f} Cr (within 5%)"})
        else:
            checks.append({"id":1, "name":"Invoice ↔ PO total", "status":"FAIL",
                           "detail":f"₹{inv_total/1e7:.2f} Cr vs ₹{po_total/1e7:.2f} Cr ({v*100:.1f}% variance, threshold 5%)"})
    else:
        checks.append({"id":1, "name":"Invoice ↔ PO total", "status":"FAIL",
                       "detail":"no PO linked — cannot 3-way match"})

    # 2. AI release control: PDF total (tax-inclusive) vs ERP invoice total, 1% tolerance.
    #    Mirrors the pipeline rule that sets gold_fact_invoices.release_blocked.
    if release_blocked:
        checks.append({"id":2, "name":"AI release control (PDF ↔ ERP total)", "status":"FAIL",
                       "detail":f"RELEASE BLOCKED — {r.get('block_reason') or 'PDF disagrees with ERP'}"
                                + (f"; PDF ₹{ex_total:,.0f} vs ERP ₹{inv_total:,.0f}" if ex_total else "")})
    elif ex_total:
        v = _ratio(ex_total, inv_total)
        status = "PASS" if v <= 0.01 else "FAIL"
        checks.append({"id":2, "name":"AI release control (PDF ↔ ERP total)", "status":status,
                       "detail":f"PDF ₹{ex_total:,.0f} vs ERP ₹{inv_total:,.0f} ({v*100:.1f}% variance, tolerance 1%)"})
    else:
        checks.append({"id":2, "name":"AI release control (PDF ↔ ERP total)", "status":"WARN",
                       "detail":"no PDF on file / total not extracted"})

    # 3. ERP vendor vs PDF vendor (case + punctuation-insensitive)
    if not ex_vendor:
        checks.append({"id":3, "name":"ERP vendor ↔ PDF vendor", "status":"WARN",
                       "detail":"PDF vendor not extracted"})
    elif erp_vendor == ex_vendor or erp_vendor.replace("-","").replace(" ","") == ex_vendor.replace("-","").replace(" ",""):
        checks.append({"id":3, "name":"ERP vendor ↔ PDF vendor", "status":"PASS",
                       "detail":f"'{r.get('vendor_name')}' matches PDF"})
    else:
        checks.append({"id":3, "name":"ERP vendor ↔ PDF vendor", "status":"FAIL",
                       "detail":f"ERP='{r.get('vendor_name')}' vs PDF='{r.get('extracted_vendor_name')}'"})

    # 4. GSTIN match (UC column masks hide GSTINs from non-controllers → WARN, not FAIL)
    def _masked(v: str) -> bool:
        return "XXXX" in v or "*" in v
    if _masked(ex_gstin) or _masked(erp_gstin):
        checks.append({"id":4, "name":"GSTIN match", "status":"WARN",
                       "detail":"GSTIN masked by Unity Catalog policy (finance_controllers only)"})
    elif not ex_gstin:
        checks.append({"id":4, "name":"GSTIN match", "status":"WARN",
                       "detail":"PDF GSTIN not extracted"})
    elif not erp_gstin:
        checks.append({"id":4, "name":"GSTIN match", "status":"WARN",
                       "detail":"vendor master GSTIN is NULL"})
    elif erp_gstin == ex_gstin:
        checks.append({"id":4, "name":"GSTIN match", "status":"PASS",
                       "detail":f"{erp_gstin} ✓"})
    else:
        checks.append({"id":4, "name":"GSTIN match", "status":"FAIL",
                       "detail":f"ERP={erp_gstin} vs PDF={ex_gstin}"})

    # 5. PO reference match
    if not ex_po:
        checks.append({"id":5, "name":"PO reference match", "status":"WARN",
                       "detail":"PDF PO reference not extracted"})
    elif erp_po == ex_po:
        checks.append({"id":5, "name":"PO reference match", "status":"PASS",
                       "detail":f"{erp_po} ✓"})
    else:
        checks.append({"id":5, "name":"PO reference match", "status":"FAIL",
                       "detail":f"ERP={erp_po} vs PDF={ex_po}"})

    # 6. Vendor master integrity
    issues = []
    if not erp_gstin: issues.append("GSTIN NULL")
    if r.get("vendor_country") == "USA" and r.get("vendor_state") in ("Bihar", "Telangana", "Kerala", "Tamil Nadu", "Karnataka", "Maharashtra"):
        issues.append(f"country=USA but state={r.get('vendor_state')} — inconsistent")
    if not r.get("vendor_is_active"):
        issues.append("vendor not active")
    if issues:
        checks.append({"id":6, "name":"Vendor master integrity", "status":"WARN",
                       "detail":"; ".join(issues)})
    else:
        checks.append({"id":6, "name":"Vendor master integrity", "status":"PASS",
                       "detail":"vendor record consistent"})

    # 7. Duplicate-payment check
    dup_rows = await asyncio.to_thread(db.query, f"""
        SELECT COUNT(*) AS dups
        FROM {CATALOG}.{SCHEMA}.gold_fact_invoices
        WHERE vendor_id = %(v)s AND invoice_amount = %(a)s
          AND invoice_id != %(id)s
          AND invoice_date > DATE_SUB(current_date(), 90)
    """, {"v": r.get("vendor_id"), "a": inv_amt, "id": r.get("invoice_id")})
    dup_count = int((dup_rows or [{}])[0].get("dups", 0))
    if dup_count > 0:
        checks.append({"id":7, "name":"Duplicate payment check", "status":"FAIL",
                       "detail":f"{dup_count} other invoice(s) from same vendor for ₹{inv_amt:,.0f} in last 90 days"})
    else:
        checks.append({"id":7, "name":"Duplicate payment check", "status":"PASS",
                       "detail":"no duplicates in last 90 days"})

    # 8. AP sub-ledger ↔ GL tie-out, read from gold_recon_subledger_vs_gl (not asserted)
    recon = await asyncio.to_thread(db.get_subledger_gl_recon)
    ap = next((x for x in recon["rows"] if x["account_code"] == "2000"), None)
    if ap is None:
        checks.append({"id":8, "name":"AP sub-ledger ↔ GL tie-out", "status":"WARN",
                       "detail":"reconciliation row for account 2000 not found"})
    elif ap["tied"]:
        checks.append({"id":8, "name":"AP sub-ledger ↔ GL tie-out", "status":"PASS",
                       "detail":f"tied: Δ ₹{ap['delta']:,.0f} fully explained by {ap['reconciling_items_count']} reconciling item(s)"})
    else:
        checks.append({"id":8, "name":"AP sub-ledger ↔ GL tie-out", "status":"WARN",
                       "detail":f"unexplained Δ ₹{ap['unexplained_delta']:,.0f} on account 2000"})

    # Recommendation
    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")
    if release_blocked:
        rec = {"label": "HOLD", "tone": "danger",
               "reason": f"Payment release blocked by the AI control: {r.get('block_reason') or 'PDF disagrees with ERP'}"}
    elif fail_count > 0:
        rec = {"label": "REJECT", "tone": "danger",
               "reason": f"{fail_count} hard failures: " + ", ".join([c["name"] for c in checks if c["status"] == "FAIL"])}
    elif warn_count > 0:
        rec = {"label": "HOLD", "tone": "warning",
               "reason": f"{warn_count} warning(s) need a human eye"}
    else:
        rec = {"label": "APPROVE", "tone": "success", "reason": "All 8 checks passed."}

    return {
        "invoice_id": r.get("invoice_id"),
        "invoice_number": r.get("invoice_number"),
        "vendor_name": r.get("vendor_name"),
        "release_blocked": release_blocked,
        "block_reason": r.get("block_reason"),
        "erp_total": inv_total,
        "pdf_total": ex_total or None,
        "checks": checks,
        "recommendation": rec,
    }


@app.get("/api/recon")
async def get_recon():
    """Sub-ledger ↔ GL reconciliation at the GL cut-off.

    Returns {"rows": [...], "all_tied": bool}; one row per control account
    (AR=1100, AP=2000) with subledger_amount, gl_amount, delta,
    reconciling_items_amount/count, unexplained_delta, tied, cutoff_date and the
    documented reconciling items. tied ⇔ |unexplained_delta| < ₹1.
    """
    return await asyncio.to_thread(db.get_subledger_gl_recon)


@app.get("/api/ap/exception-queue")
async def ap_exception_queue(limit: int = Query(200, ge=1, le=500)):
    """AP exception queue served from Lakebase (synced from Gold); warehouse fallback is flagged."""
    rows = await asyncio.to_thread(lakebase.get_ap_exception_queue, limit)
    if rows is not None:
        return {"source": "lakebase", "rows": rows}
    rows = await asyncio.to_thread(db.get_ap_exception_queue_from_warehouse, limit)
    return {"source": "warehouse", "rows": rows}


@app.get("/api/ap/exception-queue/{invoice_id}")
async def ap_exception_queue_item(invoice_id: str):
    """Low-latency lookup of one queued invoice (Lakebase), with its latest approval action."""
    rows = await asyncio.to_thread(lakebase.get_ap_exception_queue, 1, invoice_id)
    source = "lakebase"
    if rows is None:
        rows = await asyncio.to_thread(db.get_ap_exception_queue_from_warehouse, 1, invoice_id)
        source = "warehouse"
    if not rows:
        return JSONResponse({"error": f"{invoice_id} not in the exception queue"}, status_code=404)
    return {"source": source, "row": rows[0]}


@app.get("/api/summary/{tab}")
async def get_summary(tab: str):
    """LLM-generated glance summary for the given tab (P2P / O2C / R2R)."""
    if tab.upper() not in {"P2P", "O2C", "R2R"}:
        return JSONResponse({"error": "tab must be P2P, O2C, or R2R"}, status_code=400)
    if DEMO_MODE:
        return {"tab": tab.upper(), "bullets": ["- Demo mode — live summary disabled"],
                "as_of": None, "demo": True}
    try:
        return await summary_mod.generate_summary(tab)
    except (db.WarehouseUnavailable, db.QueryError):
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.get("/api/metrics/p2p")
async def metrics_p2p():
    try:
        metrics = await asyncio.to_thread(db.get_p2p_metrics)
        payment_run = await asyncio.to_thread(db.get_payment_run_data)
        return {"metrics": metrics, "payment_run": payment_run}
    except (db.WarehouseUnavailable, db.QueryError):
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/metrics/o2c")
async def metrics_o2c():
    try:
        metrics = await asyncio.to_thread(db.get_o2c_metrics)
        return {"metrics": metrics}
    except (db.WarehouseUnavailable, db.QueryError):
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/metrics/r2r")
async def metrics_r2r():
    try:
        metrics = await asyncio.to_thread(db.get_r2r_metrics)
        return {"metrics": metrics}
    except (db.WarehouseUnavailable, db.QueryError):
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── SSE Streams ──
# Use StreamingResponse with X-Accel-Buffering: no so the Databricks Apps
# nginx proxy does not buffer events before delivering them to the browser.

_SSE_HEADERS = {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@app.get("/stream/p2p")
async def sse_p2p(request: Request):
    async def generate():
        async for event in stream_p2p():
            if await request.is_disconnected():
                break
            yield f"data: {event}\n\n"
    return StreamingResponse(generate(), headers=_SSE_HEADERS)


@app.get("/stream/o2c")
async def sse_o2c(request: Request):
    async def generate():
        async for event in stream_o2c():
            if await request.is_disconnected():
                break
            yield f"data: {event}\n\n"
    return StreamingResponse(generate(), headers=_SSE_HEADERS)


@app.get("/stream/r2r")
async def sse_r2r(request: Request):
    async def generate():
        async for event in stream_r2r():
            if await request.is_disconnected():
                break
            yield f"data: {event}\n\n"
    return StreamingResponse(generate(), headers=_SSE_HEADERS)


# ── AI Chat ──

class ChatRequest(BaseModel):
    question: str
    active_tab: str = "P2P"
    session_id: str = ""   # client supplies UUID; server generates one if blank
    previous_response_id: str = ""  # Mosaic AI Agent response ID for stateful continuity


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    """Stream the MAS response via Server-Sent Events.

    SSE event types:
      data: {"type": "chunk",  "text": "..."}
      data: {"type": "done",   "session_id": "...", "previous_response_id": "...", "routing": {...}}
      data: {"type": "error",  "message": "..."}
    """
    session_id = req.session_id.strip() or str(uuid.uuid4())
    prev_response_id = req.previous_response_id.strip() or None
    user_token = request.headers.get("x-forwarded-access-token")
    user_email = request.headers.get("x-forwarded-email", "anonymous")

    # Load Lakebase history to replay prior turns in the input array
    history = await asyncio.to_thread(lakebase.get_session_messages, session_id, 10)
    if history:
        messages = list(history[-20:])
        messages.append({"role": "user", "content": req.question})
    else:
        messages = [{"role": "user", "content": req.question}]

    async def generate():
        full_answer = ""
        response_id = None
        tool_name = None
        done_ev: dict = {}

        try:
            async for event in stream_mas_agent(messages, user_token=user_token, previous_response_id=prev_response_id, active_tab=req.active_tab):
                if event["type"] == "chunk":
                    full_answer += event["text"]
                    yield f"data: {json.dumps({'type': 'chunk', 'text': event['text']})}\n\n"
                elif event["type"] == "done":
                    response_id = event.get("response_id")
                    tool_name = event.get("tool")
                    done_ev = event
                elif event["type"] == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': event['message']})}\n\n"
                    return
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        if not full_answer.strip():
            full_answer = "The agent returned no answer. Please try rephrasing."
            yield f"data: {json.dumps({'type': 'chunk', 'text': full_answer})}\n\n"

        # Persist this turn to Lakebase
        route = done_ev.get("route") or select_route()
        routing_info = {
            "domain": "Finance Agent",
            "route": route,
            "explanation": {"genie": "Genie Agent (Conversation API)",
                            "mas": "Agent Bricks supervisor",
                            "sql_agent": "Claude + guarded SQL (fallback)"}.get(route, route),
            "tool": tool_name,
            "auth": done_ev.get("auth"),
            "row_count": done_ev.get("row_count"),
        }
        await asyncio.to_thread(
            lakebase.log_chat,
            session_id, user_email, req.active_tab, req.question,
            AGENT_ENDPOINT, full_answer, done_ev.get("sql") or "", routing_info, response_id,
        )

        done_payload = {
            "type": "done",
            "session_id": session_id,
            "previous_response_id": response_id or "",
            "routing": routing_info,
            "agent": AGENT_ENDPOINT,
            "sql": done_ev.get("sql"),
        }
        yield f"data: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Session History ──

@app.get("/api/my-sessions")
async def my_sessions(request: Request):
    """Return session cards for the current user, most recent first."""
    user = request.headers.get("x-forwarded-email", "anonymous")
    try:
        sessions = await asyncio.to_thread(lakebase.get_user_sessions, user)
        return {"sessions": sessions}
    except Exception as e:
        return {"sessions": [], "error": str(e)}


@app.get("/api/session/{session_id}")
async def get_session(session_id: str, request: Request):
    """Return full Q&A history + last previous_response_id for a session."""
    user = request.headers.get("x-forwarded-email", "anonymous")
    try:
        detail = await asyncio.to_thread(lakebase.get_session_detail, session_id, user)
        return {
            "session_id": session_id,
            "messages": detail.get("messages", []),
            "previous_response_id": detail.get("previous_response_id"),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Lakebase: AP Approvals ──

class ApprovalRequest(BaseModel):
    invoice_id: str
    action: str  # APPROVED, REJECTED, ESCALATED
    reason: str = ""

@app.post("/api/approve")
async def approve_invoice(req: ApprovalRequest, request: Request):
    user = request.headers.get("x-forwarded-email", "unknown")
    try:
        # Write path uses the app service principal (Lakebase), independent of the user's token.
        await asyncio.to_thread(lakebase.log_approval, req.invoice_id, req.action, req.reason, user)
        return {"status": "logged", "action": req.action, "invoice_id": req.invoice_id,
                "persisted_to": "lakebase" if lakebase.is_connected() else "memory"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})



# ── Escalation: AP Exceptions via Databricks SQL Alert ───────────────────────

class EscalateRequest(BaseModel):
    exception_types: list[str]  # e.g. ["AMOUNT_MISMATCH", "NO_PO_REFERENCE"]

@app.post("/api/escalate/p2p")
async def escalate_p2p(req: EscalateRequest, request: Request):
    """
    Create/update a Databricks SQL Alert for the selected exception types
    and unpause it so Databricks fires the email within ~60 seconds.
    Recipient is set via ESCALATION_RECIPIENT env var — not from the UI.
    Uses the forwarded user token so the alert is created with the user's
    workspace permissions (avoids SP non-admin restriction on notification
    destinations).
    """
    user_token = request.headers.get("x-forwarded-access-token")
    try:
        result = await asyncio.to_thread(escalate.run_escalation, req.exception_types, user_token)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Lakebase: AR Call Logs ──

class CallLogRequest(BaseModel):
    customer_id: str
    customer_name: str = ""
    outcome: str  # REACHED_PTP, REACHED_DISPUTE, VOICEMAIL, ESCALATE
    ptp_date: str | None = None
    notes: str = ""

@app.post("/api/call-log")
async def call_log(req: CallLogRequest, request: Request):
    user = request.headers.get("x-forwarded-email", "unknown")
    try:
        await asyncio.to_thread(
            lakebase.log_call, req.customer_id, req.customer_name,
            req.outcome, req.ptp_date, req.notes, user
        )
        return {"status": "logged", "outcome": req.outcome}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Lakebase: User History ──

@app.get("/api/my-approvals")
async def my_approvals(request: Request):
    user = request.headers.get("x-forwarded-email", "unknown")
    try:
        approvals = await asyncio.to_thread(lakebase.get_user_approvals, user)
        return {"approvals": approvals}
    except Exception as e:
        return {"approvals": [], "error": str(e)}


# ── Invoice Viewer ──

def _build_invoice_response(row: dict) -> dict:
    """Coerce a DB row or demo dict to the invoice response shape."""
    # pdf_file_path comes from gold_fact_invoices (via silver_invoice_extractions join)
    # or from bronze_raw_invoice_documents fallback join
    pdf_path = row.get("pdf_file_path") or row.get("file_path") or ""
    data_source = row.get("data_source") or ("ERP_AND_PDF" if pdf_path else "ERP_ONLY")
    match_status = row.get("match_status") or ""
    _matched = {"THREE_WAY_MATCHED", "TWO_WAY_MATCHED"}
    return {
        "invoice_id":        row.get("invoice_id"),
        "invoice_number":    row.get("invoice_number"),
        "quarantine_reason": row.get("quarantine_reason") or (match_status if match_status not in _matched else None),
        "vendor_id":         row.get("vendor_id"),
        "vendor_name":       row.get("vendor_name"),
        "po_id":             row.get("po_id"),
        "invoice_date":      str(row.get("invoice_date") or ""),
        "due_date":          str(row.get("due_date") or ""),
        "invoice_amount":    float(row.get("invoice_amount") or 0),
        # invoice_total = invoice_amount + tax (i.e. invoice_total_inr in the gold table).
        # Renamed from the prior overloaded `po_amount` so the UI shows them distinctly.
        "invoice_total":     float(row.get("invoice_total") or row.get("invoice_total_inr") or row.get("invoice_amount") or 0),
        # po_amount = the REAL PO total from silver_po_header.total_amount.
        # NULL when the invoice has no linked PO (NO_PO_REFERENCE).
        "po_amount":         float(row.get("po_amount") or 0),
        "status":            row.get("status") or row.get("invoice_status"),
        "gstin":             row.get("gstin_vendor") or row.get("gstin"),
        "payment_terms":     row.get("payment_terms"),
        "raw_text":          row.get("raw_text") or "",
        "file_path":         pdf_path,
        # AI extraction fields — surfaced so the UI can render side-by-side ERP vs PDF.
        "extracted_vendor_name":    row.get("extracted_vendor_name"),
        "extracted_invoice_number": row.get("extracted_invoice_number"),
        "extracted_total_amount":   float(row["extracted_total_amount"]) if row.get("extracted_total_amount") is not None else None,
        "extracted_subtotal":       float(row["extracted_subtotal"]) if row.get("extracted_subtotal") is not None else None,
        "extracted_gstin":          row.get("extracted_gstin"),
        "extracted_po_reference":   row.get("extracted_po_reference"),
        # Data provenance fields — used by the UI to show source badges and conditionally show PDF
        "data_source":       data_source,
        "has_source_pdf":    bool(pdf_path),
        # AI release control (gold_fact_invoices.release_blocked)
        "release_blocked":   bool(row.get("release_blocked")),
        "block_reason":      row.get("block_reason"),
        "legal_entity":      row.get("legal_entity"),
    }


def _demo_invoice_fallback(invoice_id: str) -> dict | None:
    """Fixture invoice — ONLY when DEMO_MODE=true. Otherwise unknown IDs are a 404."""
    if not DEMO_MODE:
        return None
    return {
        "invoice_id": invoice_id, "invoice_number": invoice_id, "quarantine_reason": None,
        "vendor_id": "DEMO", "vendor_name": "Demo Vendor (fixture)", "po_id": "",
        "invoice_date": "", "due_date": "", "invoice_amount": 0.0, "po_amount": 0.0,
        "status": "DEMO", "gstin": "", "payment_terms": "", "raw_text": "", "file_path": "",
        "data_source": "DEMO", "has_source_pdf": False,
    }


@app.get("/api/invoice/{invoice_id}")
async def get_invoice(invoice_id: str):
    """
    Return full invoice details for any invoice ID or ERP invoice_number.
    Searches in order: gold_fact_invoices → silver_invoice_exceptions → bronze_p2p_invoices.
    Falls back to demo data when the warehouse is unavailable.
    """
    import re as _re
    is_erp_number = bool(_re.match(r'^VINV-\d{4}-\d+$', invoice_id))
    gold_col  = "i.invoice_number" if is_erp_number else "i.invoice_id"
    exc_col   = "e.invoice_number" if is_erp_number else "e.invoice_id"
    bronze_col = "b.invoice_number" if is_erp_number else "b.invoice_id"

    try:
        # Skip warehouse queries immediately if in demo mode (warehouse unavailable)
        if DEMO_MODE:
            return _build_invoice_response(_demo_invoice_fallback(invoice_id))



        # 1️⃣ Primary: gold_fact_invoices — pdf_file_path and data_source come directly from gold
        rows = await asyncio.to_thread(db.query, f"""
            SELECT
                i.invoice_id,
                i.invoice_number,
                i.match_status,
                i.vendor_id,
                v.vendor_name,
                i.po_id,
                i.invoice_date,
                i.due_date,
                i.invoice_amount,
                i.invoice_total_inr AS invoice_total,
                p.total_amount      AS po_amount,
                i.invoice_status    AS status,
                i.gstin_vendor,
                NULL                AS payment_terms,
                i.pdf_file_path,
                i.data_source,
                i.release_blocked,
                i.block_reason,
                i.legal_entity,
                x.extracted_vendor_name,
                x.extracted_total_amount,
                x.extracted_gstin,
                x.extracted_po_reference,
                x.extracted_invoice_number,
                x.extracted_subtotal
            FROM {CATALOG}.{SCHEMA}.gold_fact_invoices i
            LEFT JOIN {CATALOG}.{SCHEMA}.gold_dim_vendor v ON i.vendor_id = v.vendor_id
            LEFT JOIN {CATALOG}.{SCHEMA}.silver_po_header p ON i.po_id = p.po_id
            LEFT JOIN {CATALOG}.{SCHEMA}.silver_invoice_extractions x ON i.invoice_id = x.invoice_id
            WHERE {gold_col} = %(invoice_id)s
            LIMIT 1
        """, {"invoice_id": invoice_id})

        # 2️⃣ Fallback: silver_invoice_exceptions (joined with silver_po_header for the real PO total)
        if not rows:
            rows = await asyncio.to_thread(db.query, f"""
                SELECT
                    e.invoice_id, e.invoice_number,
                    e.exception_type AS match_status,
                    e.vendor_id, v.vendor_name, e.po_id,
                    e.invoice_date, e.due_date, e.invoice_amount,
                    e.total_amount AS invoice_total,
                    p.total_amount AS po_amount,
                    e.status, e.gstin_vendor, e.payment_terms,
                    NULL AS pdf_file_path, 'ERP_ONLY' AS data_source,
                    NULL AS extracted_vendor_name, NULL AS extracted_total_amount,
                    NULL AS extracted_gstin, NULL AS extracted_po_reference,
                    NULL AS extracted_invoice_number, NULL AS extracted_subtotal
                FROM {CATALOG}.{SCHEMA}.silver_invoice_exceptions e
                LEFT JOIN {CATALOG}.{SCHEMA}.bronze_vendors v ON e.vendor_id = v.vendor_id
                LEFT JOIN {CATALOG}.{SCHEMA}.silver_po_header p ON e.po_id = p.po_id
                WHERE {exc_col} = %(invoice_id)s
                LIMIT 1
            """, {"invoice_id": invoice_id})

        # 3️⃣ Last resort: bronze_p2p_invoices (joined with silver_po_header for the real PO total)
        if not rows:
            rows = await asyncio.to_thread(db.query, f"""
                SELECT
                    b.invoice_id, b.invoice_number,
                    NULL AS match_status,
                    b.vendor_id, v.vendor_name, b.po_id,
                    b.invoice_date, b.due_date, b.invoice_amount,
                    b.total_amount AS invoice_total,
                    p.total_amount AS po_amount,
                    b.status, b.gstin_vendor, b.payment_terms,
                    NULL AS pdf_file_path, 'ERP_ONLY' AS data_source,
                    NULL AS extracted_vendor_name, NULL AS extracted_total_amount,
                    NULL AS extracted_gstin, NULL AS extracted_po_reference,
                    NULL AS extracted_invoice_number, NULL AS extracted_subtotal
                FROM {CATALOG}.{SCHEMA}.bronze_p2p_invoices b
                LEFT JOIN {CATALOG}.{SCHEMA}.bronze_vendors v ON b.vendor_id = v.vendor_id
                LEFT JOIN {CATALOG}.{SCHEMA}.silver_po_header p ON b.po_id = p.po_id
                WHERE {bronze_col} = %(invoice_id)s
                LIMIT 1
            """, {"invoice_id": invoice_id})

        if rows:
            return _build_invoice_response(rows[0])
        return JSONResponse(status_code=404, content={"error": f"invoice {invoice_id} not found"})

    except (db.WarehouseUnavailable, db.QueryError):
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


async def _fetch_pdf_from_volume(file_path: str, user_token: str | None = None) -> bytes | None:
    """
    Fetch a PDF from UC Volume using the Databricks SDK's Files API.
    Returns pdf bytes on success, None on failure.
    """
    if not file_path or not file_path.lower().endswith(".pdf"):
        return None

    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        # SDK uses .files.download(); returns a stream-like with .contents
        result = w.files.download(file_path)
        # result.contents is a BinaryIO-like; read everything
        data = result.contents.read() if hasattr(result, "contents") else bytes(result)
        print(f"[volume] fetched {file_path} ({len(data)} bytes) via SDK")
        return data
    except Exception as e:
        print(f"[volume] SDK fetch failed for {file_path}: {type(e).__name__}: {e}")

    # Last-ditch fallback: raw HTTPS with SP token (helpful for diagnostic logging)
    try:
        import urllib.request as _url_req
        from backend.config import get_workspace_host, get_token as _cfg_get_token
        host = get_workspace_host()
        token = user_token or _cfg_get_token()
        if not host or not token:
            print(f"[volume] no host/token for raw fallback: host_set={bool(host)} token_set={bool(token)}")
            return None
        url = f"{host.rstrip('/')}/api/2.0/fs/files{file_path}"
        req = _url_req.Request(url, headers={"Authorization": f"Bearer {token}"})
        with _url_req.urlopen(req, timeout=15) as resp:
            data = resp.read()
            print(f"[volume] raw fetch OK: {file_path} ({len(data)} bytes)")
            return data
    except Exception as e:
        print(f"[volume] raw fetch failed for {file_path}: {type(e).__name__}: {e}")
        return None


@app.get("/api/invoice/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: str, request: Request, download: bool = Query(False)):
    """
    Serve the PDF for the given invoice.

    Priority:
      1. Fetch the original PDF from UC Volume (raw_invoices/<invoice_id>.pdf)
         — this is the actual source document that ai_parse_document processed
      2. Fall back to dynamically building a PDF from ERP metadata
    Falls back to demo data when the warehouse is unreachable.
    """
    import re as _re
    is_erp_number = bool(_re.match(r'^VINV-\d{4}-\d+$', invoice_id))
    gold_col   = "i.invoice_number" if is_erp_number else "i.invoice_id"
    exc_col    = "e.invoice_number" if is_erp_number else "e.invoice_id"
    bronze_col = "b.invoice_number" if is_erp_number else "b.invoice_id"

    # User token for Files API — forwarded by Databricks Apps proxy
    user_token = request.headers.get("x-forwarded-access-token")

    def _disposition(fname: str) -> str:
        return f'attachment; filename="{fname}"' if download else f'inline; filename="{fname}"'

    try:
        # Skip warehouse queries immediately if in demo mode
        if DEMO_MODE:
            erp = _build_invoice_response(_demo_invoice_fallback(invoice_id))
            pdf_bytes = await asyncio.to_thread(build_invoice_pdf, erp, "")
            return Response(content=pdf_bytes, media_type="application/pdf",
                            headers={"Content-Disposition": _disposition(f"invoice-{invoice_id}.pdf")})

        # 1️⃣ gold_fact_invoices — join silver_po_header for the REAL PO total
        rows = await asyncio.to_thread(db.query, f"""
            SELECT
                i.invoice_id, i.invoice_number, i.match_status,
                i.vendor_id, v.vendor_name, i.po_id,
                i.invoice_date, i.due_date, i.invoice_amount,
                i.invoice_total_inr AS invoice_total,
                p.total_amount      AS po_amount,
                i.invoice_status AS status, i.gstin_vendor, NULL AS payment_terms,
                i.pdf_file_path, i.data_source
            FROM {CATALOG}.{SCHEMA}.gold_fact_invoices i
            LEFT JOIN {CATALOG}.{SCHEMA}.gold_dim_vendor v ON i.vendor_id = v.vendor_id
            LEFT JOIN {CATALOG}.{SCHEMA}.silver_po_header p ON i.po_id = p.po_id
            WHERE {gold_col} = %(invoice_id)s
            LIMIT 1
        """, {"invoice_id": invoice_id})

        # 2️⃣ silver_invoice_exceptions
        if not rows:
            rows = await asyncio.to_thread(db.query, f"""
                SELECT
                    e.invoice_id, e.invoice_number, e.exception_type AS match_status,
                    e.vendor_id, v.vendor_name, e.po_id,
                    e.invoice_date, e.due_date, e.invoice_amount,
                    e.total_amount AS invoice_total,
                    p.total_amount AS po_amount,
                    e.status, e.gstin_vendor, e.payment_terms,
                    NULL AS pdf_file_path, 'ERP_ONLY' AS data_source
                FROM {CATALOG}.{SCHEMA}.silver_invoice_exceptions e
                LEFT JOIN {CATALOG}.{SCHEMA}.bronze_vendors v ON e.vendor_id = v.vendor_id
                LEFT JOIN {CATALOG}.{SCHEMA}.silver_po_header p ON e.po_id = p.po_id
                WHERE {exc_col} = %(invoice_id)s
                LIMIT 1
            """, {"invoice_id": invoice_id})

        # 3️⃣ bronze_p2p_invoices
        if not rows:
            rows = await asyncio.to_thread(db.query, f"""
                SELECT
                    b.invoice_id, b.invoice_number, NULL AS match_status,
                    b.vendor_id, v.vendor_name, b.po_id,
                    b.invoice_date, b.due_date, b.invoice_amount,
                    b.total_amount AS invoice_total,
                    p.total_amount AS po_amount,
                    b.status, b.gstin_vendor, b.payment_terms,
                    NULL AS pdf_file_path, 'ERP_ONLY' AS data_source
                FROM {CATALOG}.{SCHEMA}.bronze_p2p_invoices b
                LEFT JOIN {CATALOG}.{SCHEMA}.bronze_vendors v ON b.vendor_id = v.vendor_id
                LEFT JOIN {CATALOG}.{SCHEMA}.silver_po_header p ON b.po_id = p.po_id
                WHERE {bronze_col} = %(invoice_id)s
                LIMIT 1
            """, {"invoice_id": invoice_id})

        if not rows:
            return JSONResponse(status_code=404, content={"error": f"invoice {invoice_id} not found"})
        erp = _build_invoice_response(rows[0])
        file_path = erp.get("file_path", "")

        # Try to serve the actual source PDF from UC Volume
        if file_path:
            pdf_bytes = await _fetch_pdf_from_volume(file_path, user_token)
            if pdf_bytes:
                filename = file_path.split("/")[-1] or f"invoice-{invoice_id}.pdf"
                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers={"Content-Disposition": _disposition(filename)},
                )

        # Fall back: build a PDF from ERP metadata
        pdf_bytes = await asyncio.to_thread(build_invoice_pdf, erp, "")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": _disposition(f"invoice-{invoice_id}.pdf")},
        )

    except (db.WarehouseUnavailable, db.QueryError):
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─── Static Files (React build) ─────────────────────────────

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    # Mount assets directory for JS/CSS
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # Serve other static files (favicon, etc.)
    @app.get("/vite.svg")
    async def vite_svg():
        f = static_dir / "vite.svg"
        if f.exists():
            return FileResponse(str(f))
        return JSONResponse(status_code=404, content={"error": "not found"})

    # SPA fallback — must be last
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't catch API/stream routes
        if full_path.startswith("api/") or full_path.startswith("stream/"):
            return JSONResponse(status_code=404, content={"error": "not found"})
        index = static_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse(status_code=404, content={"error": "Frontend not built. Run: cd frontend && npm run build"})
else:
    @app.get("/")
    async def root():
        return {"message": "Finance Operations API. Frontend not built yet.",
                "hint": "Run: cd frontend && npm run build && cp -r frontend/dist/* backend/static/"}
