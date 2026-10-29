"""Finance AI Chat — question routing.

Route order (first configured wins):
  1. MAS_ENDPOINT_NAME set  → Agent Bricks supervisor (Responses API format)
  2. GENIE_SPACE_ID set     → Genie Conversation API (start-conversation → poll →
                              query-result). The Genie space is the governed,
                              curated natural-language interface over the Gold tables.
  3. last resort            → built-in Claude + SQL agent; the generated SQL is
                              checked by backend.sql_guard before it runs.

All calls use the signed-in user's token (on-behalf-of-user) when the Databricks
Apps proxy forwards one, so Unity Catalog permissions, row filters and column
masks apply to chat answers too. The app service principal is the fallback.

Session history is persisted to Lakebase (falls back to in-memory).
"""
import asyncio
import json
import os
import re
import aiohttp
from backend import db
from backend.config import get_workspace_host, get_token, CATALOG, SCHEMA, GENIE_SPACE_ID, optional_env
from backend.sql_guard import guard_sql, SqlGuardError

MAS_ENDPOINT = optional_env("MAS_ENDPOINT_NAME")
AGENT_ENDPOINT = (MAS_ENDPOINT
                  or (f"genie-space:{GENIE_SPACE_ID}" if GENIE_SPACE_ID else "")
                  or "finance-sql-agent (Claude + guarded SQL fallback)")
FMAPI_MODEL = MAS_ENDPOINT     # backwards-compat

# Foundation model used by the built-in fallback agent (no MAS endpoint required).
FOUNDATION_MODEL = os.environ.get("FMAPI_MODEL", "databricks-claude-sonnet-4-5")

GENIE_POLL_S = float(os.environ.get("GENIE_POLL_SECONDS", "1.5"))
GENIE_TIMEOUT_S = float(os.environ.get("GENIE_TIMEOUT_SECONDS", "120"))

# Compact schema of the governed gold tables the fallback agent may query.
GOLD_SCHEMA = """
gold_fact_invoices  -- AP / Procure-to-Pay invoices (one row per invoice)
  invoice_id, invoice_number, po_id, vendor_id, vendor_name, vendor_category, legal_entity,
  invoice_date, due_date, payment_date, invoice_amount, tax_amount, invoice_total_inr,
  paid_amount_inr, invoice_status, match_status (THREE_WAY_MATCHED|TWO_WAY_MATCHED|AMOUNT_MISMATCH|NO_PO_REFERENCE|PENDING_REVIEW),
  has_po_ref, has_grn, is_overdue, aging_days, aging_bucket, days_to_pay, payment_on_time,
  days_outstanding, invoice_year, invoice_month, invoice_quarter, data_source,
  release_blocked (AI release control: the invoice PDF disagrees with the ERP), block_reason, ai_extracted_amount
  -- touchless = match_status = 'THREE_WAY_MATCHED' AND NOT release_blocked
silver_invoice_exceptions  -- every AP invoice that needs a human
  invoice_id, invoice_number, vendor_id, exception_type (DUPLICATE|EXTRACTION_MISMATCH|NO_PO_REFERENCE|
  AMOUNT_MISMATCH|MISSING_GRN|MISSING_GSTIN|CRITICAL_OVERDUE|PENDING_REVIEW), total_amount, status
gold_dim_vendor  -- vendor master + rollups
  vendor_id, vendor_name, vendor_category, payment_terms, gstin, total_invoices,
  total_spend_inr, avg_invoice_amount_inr, three_way_matched_invoices, amount_mismatch_invoices,
  total_paid_amount_inr, match_compliance_pct
gold_fact_payments  -- AP payments
  payment_id, invoice_id, vendor_id, vendor_name, payment_date, due_date, payment_amount_inr,
  invoice_total_inr, payment_method, payment_status, days_to_pay, early_late_days, payment_timing
gold_fact_collections  -- AR / Order-to-Cash invoices & collections
  o2c_invoice_id, invoice_number, customer_id, customer_name, segment, region, legal_entity, invoice_date,
  due_date, invoice_total_inr, amount_collected_inr, balance_outstanding, invoice_status,
  aging_bucket, days_outstanding, days_overdue, is_fully_collected
gold_dim_customer  -- customer master + AR rollups
  customer_id, customer_name, segment, industry, payment_terms, credit_limit,
  total_billed_inr, total_collected_inr, outstanding_ar_inr, dso, collection_rate_pct,
  overdue_invoices, credit_utilization_pct
gold_fact_sales  -- sales orders
  so_id, so_number, customer_id, customer_name, segment, so_date, status, region,
  so_total_inr, revenue_excl_tax, software_revenue_inr, services_revenue_inr
gold_fact_gl  -- GL journal lines
  je_id, je_number, account_code, account_name, account_type, cost_center, department,
  je_date, period, fiscal_year, status, debit_inr, credit_inr, net_amount_inr
gold_fact_trial_balance  -- trial balance by account & period
  fiscal_year, fiscal_quarter, period, account_code, account_name, account_type,
  period_debit, period_credit, period_net, closing_balance_inr, balance_type
gold_recon_subledger_vs_gl  -- sub-ledger vs GL reconciliation at the GL cut-off
  account_code, account_name, subledger_source, subledger_amount, gl_amount, delta,
  reconciling_items_amount, reconciling_items_count, unexplained_delta, tied, cutoff_date
gold_recon_reconciling_items  -- documented items that explain the recon delta
  account_code, document_id, document_type, amount, reason, gl_je_id, gl_je_status
gold_ai_extraction_eval  -- AI extraction accuracy and tamper-recall metrics per evaluation run
""".strip()


def _token(user_token: str | None = None) -> str:
    """On-behalf-of-user first; the app service principal when no user token is forwarded."""
    return user_token or get_token() or ""


def select_route() -> str:
    """Which backend answers chat questions: 'mas', 'genie' or 'sql_agent'."""
    if MAS_ENDPOINT:
        return "mas"
    if GENIE_SPACE_ID:
        return "genie"
    return "sql_agent"


def _markdown_table(columns: list[str], rows: list[list], cap: int = 10) -> str:
    """Compact markdown table of a query result (first `cap` rows)."""
    if not columns:
        return ""

    def cell(v):
        if v is None:
            return ""
        try:
            f = float(v)
            if abs(f) >= 1000:
                return f"{f:,.0f}"
        except (TypeError, ValueError):
            pass
        return str(v).replace("|", "\\|")

    head = "| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n"
    body = "".join("| " + " | ".join(cell(v) for v in r) + " |\n" for r in rows[:cap])
    more = f"\n_{len(rows) - cap} more row(s) not shown._\n" if len(rows) > cap else ""
    return head + body + more


def _extract_answer(output: list) -> str:
    """
    Extract the final formatted answer from the MAS output array: the LAST
    message item whose text is not just a <name> routing tag.
    """
    candidates = []
    for item in output:
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            text = c.get("text", "").strip()
            if not text:
                continue
            if text.startswith("<name>") and text.endswith("</name>"):
                continue
            candidates.append(text)
    return candidates[-1] if candidates else ""


async def _stream_text(answer: str):
    for i in range(0, len(answer), 40):
        yield {"type": "chunk", "text": answer[i:i + 40]}
        await asyncio.sleep(0.01)


# ─── Route 2: Genie Conversation API ─────────────────────────

async def _http(session, method: str, url: str, token: str, payload: dict | None = None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with session.request(method, url, json=payload, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=60)) as resp:
        body = await resp.text()
        try:
            data = json.loads(body) if body else {}
        except ValueError:
            data = {"raw": body[:500]}
        return resp.status, data


async def ask_genie(question: str, user_token: str | None = None,
                    conversation_id: str | None = None) -> dict:
    """Ask the Genie space one question.

    Returns {text, sql, columns, rows, conversation_id, message_id, status, auth}.
    Tries the user's token first (OBO); on 401/403 retries once with the app SP.
    """
    base = f"{get_workspace_host()}/api/2.0/genie/spaces/{GENIE_SPACE_ID}"
    attempts = ([("obo", user_token)] if user_token else []) + [("sp", get_token())]

    last_err = "no token available"
    async with aiohttp.ClientSession() as session:
        for auth, token in attempts:
            if not token:
                continue
            if conversation_id:
                st, d = await _http(session, "POST", f"{base}/conversations/{conversation_id}/messages",
                                    token, {"content": question})
                conv_id = conversation_id
                msg_id = d.get("message_id") or d.get("id")
            else:
                st, d = await _http(session, "POST", f"{base}/start-conversation", token,
                                    {"content": question})
                conv_id = d.get("conversation_id") or (d.get("conversation") or {}).get("id")
                msg_id = d.get("message_id") or (d.get("message") or {}).get("id")
            if st in (401, 403):
                last_err = f"HTTP {st} with {auth} token: {str(d)[:200]}"
                continue
            if st != 200 or not conv_id or not msg_id:
                raise RuntimeError(f"Genie start failed: HTTP {st}: {str(d)[:300]}")

            msg_url = f"{base}/conversations/{conv_id}/messages/{msg_id}"
            waited, msg = 0.0, {}
            while waited <= GENIE_TIMEOUT_S:
                st, msg = await _http(session, "GET", msg_url, token)
                if st != 200:
                    raise RuntimeError(f"Genie poll failed: HTTP {st}: {str(msg)[:300]}")
                if msg.get("status") in ("COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"):
                    break
                await asyncio.sleep(GENIE_POLL_S)
                waited += GENIE_POLL_S
            status = msg.get("status", "TIMEOUT")
            if status != "COMPLETED":
                raise RuntimeError(f"Genie message {status}: {str(msg.get('error'))[:300]}")

            text_parts, sql, columns, rows = [], None, [], []
            for att in msg.get("attachments") or []:
                if att.get("text"):
                    text_parts.append((att["text"] or {}).get("content", ""))
                q = att.get("query")
                if not q:
                    continue
                sql = q.get("query")
                if q.get("description"):
                    text_parts.append(q["description"])
                att_id = att.get("attachment_id") or att.get("id")
                if att_id:
                    st, qr = await _http(session, "GET", f"{msg_url}/attachments/{att_id}/query-result", token)
                    if st == 200:
                        sr = qr.get("statement_response") or qr
                        columns = [c.get("name") for c in
                                   ((sr.get("manifest") or {}).get("schema") or {}).get("columns", [])]
                        rows = (sr.get("result") or {}).get("data_array") or []
            return {"text": "\n\n".join(t for t in text_parts if t).strip(), "sql": sql,
                    "columns": columns, "rows": rows, "conversation_id": conv_id,
                    "message_id": msg_id, "status": status, "auth": auth}
    raise RuntimeError(f"Genie unauthorized: {last_err}")


async def stream_genie_agent(question: str, user_token: str | None = None,
                             previous_response_id: str | None = None):
    """Genie route: the answer text, a compact result table and the generated SQL."""
    prev = previous_response_id or ""
    conv = prev[len("genie:"):] if prev.startswith("genie:") else None
    res = await ask_genie(question, user_token=user_token, conversation_id=conv)
    parts = [res["text"] or "Genie answered with the result below."]
    if res["columns"]:
        parts.append(_markdown_table(res["columns"], res["rows"]))
    async for ev in _stream_text("\n\n".join(parts)):
        yield ev
    yield {"type": "done", "response_id": f"genie:{res['conversation_id']}", "tool": "genie",
           "route": "genie", "sql": res["sql"], "row_count": len(res["rows"]), "auth": res["auth"]}


# ─── Route 3: Claude + guarded SQL (last resort) ─────────────

async def _fmapi_chat(messages: list[dict], user_token: str | None = None,
                      max_tokens: int = 1024, temperature: float = 0.0) -> str:
    """Single-shot call to the Claude foundation model. User token first, SP on 401/403."""
    url = f"{get_workspace_host()}/serving-endpoints/{FOUNDATION_MODEL}/invocations"
    payload = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    tokens = [t for t in (user_token, get_token()) if t]
    body, status = "", 0
    async with aiohttp.ClientSession() as session:
        for token in tokens:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=90)) as resp:
                body, status = await resp.text(), resp.status
            if status not in (401, 403):
                break
    if status != 200:
        raise RuntimeError(f"FMAPI HTTP {status}: {body[:300]}")
    d = json.loads(body)
    msg = d.get("choices", [{}])[0].get("message", {})
    content = msg.get("content", "")
    if isinstance(content, list):  # some models return content parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return (content or "").strip()


def _clean_sql(text: str) -> str:
    """Strip markdown fences / prose. Policy is enforced by sql_guard, not here."""
    m = re.search(r"```(?:sql)?\s*(.+?)```", text, re.DOTALL | re.IGNORECASE)
    sql = (m.group(1) if m else text).strip().rstrip(";").strip()
    m2 = re.search(r"(?is)\b(with|select)\b", sql)
    if m2:
        sql = sql[m2.start():].strip()
    return sql


async def stream_sql_agent(question: str, active_tab: str = "P2P",
                           user_token: str | None = None, history: list[dict] | None = None):
    """Built-in finance agent: Claude writes SQL over the gold tables, sql_guard
    validates it (single SELECT, allow-listed tables, LIMIT ≤ 100), it runs on the
    warehouse as the user, and Claude narrates the result."""
    domain = {"P2P": "Accounts Payable (P2P)", "O2C": "Accounts Receivable (O2C)",
              "R2R": "General Ledger / close (R2R)"}.get(active_tab, active_tab)

    ctx = ""
    if history:
        recent = [f"{m.get('role')}: {m.get('content','')}" for m in history[-4:] if m.get("content")]
        if recent:
            ctx = "\n\nPrior conversation (for context):\n" + "\n".join(recent)

    sql_prompt = [
        {"role": "system", "content":
            "You are a Databricks SQL analyst for a Finance & Accounting control tower. "
            "Write ONE Databricks SQL SELECT query (no DML/DDL) over ONLY these governed gold tables "
            "to answer the user's question. Reference every table fully-qualified as "
            f"`{CATALOG}`.`{SCHEMA}`.<table_name>. "
            "Always add a LIMIT (<=100). Use current_date() for relative dates. "
            f"The user is on the {domain} tab. Output ONLY the SQL, no prose, no comments.\n\n"
            f"GOLD TABLES (all in `{CATALOG}`.`{SCHEMA}`):\n{GOLD_SCHEMA}"},
        {"role": "user", "content": question + ctx},
    ]

    async def _generate(prompt) -> str:
        return guard_sql(_clean_sql(await _fmapi_chat(prompt, user_token=user_token, max_tokens=700)),
                         CATALOG, SCHEMA)

    try:
        sql = await _generate(sql_prompt)
    except SqlGuardError as e:
        yield {"type": "error", "message": f"Generated SQL rejected by policy: {e}"}
        return
    except Exception as e:
        yield {"type": "error", "message": f"Agent (SQL generation) failed: {e}"}
        return

    try:
        rows = await asyncio.to_thread(db.query, sql)
    except db.WarehouseUnavailable as e:
        yield {"type": "error", "message": f"Warehouse unavailable: {str(e)[:200]}"}
        return
    except Exception as e:
        # One retry: let Claude repair the query given the error (re-guarded).
        try:
            sql = await _generate(sql_prompt + [
                {"role": "assistant", "content": sql},
                {"role": "user", "content": f"That query failed with: {str(e)[:300]}. Return a corrected SQL SELECT only."},
            ])
            rows = await asyncio.to_thread(db.query, sql)
        except Exception as e2:
            yield {"type": "error", "message": f"Query failed: {str(e2)[:300]}"}
            return

    preview = rows[:60]
    answer_prompt = [
        {"role": "system", "content":
            "You are a finance operations analyst. Given the user's question and the SQL result rows "
            "(JSON), write a concise, executive answer. Lead with the direct answer, then a compact "
            "markdown table of the most relevant rows (cap ~10 rows, format INR amounts readably). "
            "If there are no rows, say so plainly. Do not show the SQL."},
        {"role": "user", "content":
            f"Question: {question}\n\nSQL used:\n{sql}\n\nRows (JSON):\n{json.dumps(preview, default=str)[:6000]}"},
    ]
    try:
        answer = await _fmapi_chat(answer_prompt, user_token=user_token, max_tokens=1200)
    except Exception as e:
        yield {"type": "error", "message": f"Agent (answer) failed: {e}"}
        return

    if not answer:
        answer = f"Query returned {len(rows)} row(s), but no summary could be generated."
    async for ev in _stream_text(answer):
        yield ev
    yield {"type": "done", "response_id": None, "tool": "finance-sql-agent", "route": "sql_agent",
           "sql": sql, "row_count": len(rows), "auth": "obo" if user_token else "sp"}


# ─── Route 1: MAS supervisor; also the single entry point ────

async def stream_mas_agent(
    messages: list[dict],
    user_token: str | None = None,
    previous_response_id: str | None = None,
    active_tab: str = "P2P",
):
    """
    Entry point for chat. Routes per select_route(); falls back to the guarded
    SQL agent if Genie fails, and says so in the answer.

    Yields dicts:
      {"type": "chunk",  "text": "..."}
      {"type": "done",   "response_id": str|None, "tool": str|None, "route": "mas|genie|sql_agent",
                         "sql": str|None, "row_count": int|None, "auth": "obo|sp"}
      {"type": "error",  "message": "..."}
    """
    question = next((m.get("content", "") for m in reversed(messages)
                     if m.get("role") == "user"), "")
    history = messages[:-1] if messages else []
    route = select_route()

    if route == "genie":
        try:
            async for ev in stream_genie_agent(question, user_token=user_token,
                                               previous_response_id=previous_response_id):
                yield ev
            return
        except Exception as e:
            print(f"Genie route failed, falling back to SQL agent: {e}")
            yield {"type": "chunk", "text": f"_Genie unavailable ({str(e)[:120]}); answered by the fallback SQL agent._\n\n"}
            route = "sql_agent"

    if route == "sql_agent":
        async for ev in stream_sql_agent(question, active_tab=active_tab,
                                          user_token=user_token, history=history):
            yield ev
        return

    url = f"{get_workspace_host()}/serving-endpoints/{MAS_ENDPOINT}/invocations"
    payload = {"input": list(messages), "max_tokens": 2048}
    headers = {"Authorization": f"Bearer {_token(user_token)}", "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    yield {"type": "error", "message": f"HTTP {resp.status}: {error_text[:300]}"}
                    return
                body = await resp.text()

        answer = _extract_answer(json.loads(body).get("output", []))
        if not answer:
            yield {"type": "error", "message": "No answer returned from supervisor."}
            return
        async for ev in _stream_text(answer):
            yield ev
        yield {"type": "done", "response_id": None, "tool": None, "route": "mas",
               "sql": None, "row_count": None, "auth": "obo" if user_token else "sp"}

    except Exception as e:
        yield {"type": "error", "message": str(e)}


async def handle_chat(
    question: str,
    active_tab: str = "P2P",
    user_token: str | None = None,
    history: list[dict] | None = None,
    previous_response_id: str | None = None,
) -> dict:
    """Non-streaming wrapper: route a question and return a structured result."""
    result = {
        "question": question, "domain": active_tab,
        "routing": {"domain": "Finance Agent", "route": select_route()},
        "sql": None, "answer": None, "error": None,
        "agent": AGENT_ENDPOINT, "previous_response_id": None,
    }
    messages = list(history[-20:]) if history else []
    messages.append({"role": "user", "content": question})

    full_answer = ""
    async for event in stream_mas_agent(messages, user_token=user_token,
                                        previous_response_id=previous_response_id,
                                        active_tab=active_tab):
        if event["type"] == "chunk":
            full_answer += event["text"]
        elif event["type"] == "done":
            result["sql"] = event.get("sql")
            result["previous_response_id"] = event.get("response_id")
            result["routing"]["route"] = event.get("route")
        elif event["type"] == "error":
            result["error"] = event["message"]
            return result

    result["answer"] = full_answer.strip() or "No answer returned. Please try again."
    return result
