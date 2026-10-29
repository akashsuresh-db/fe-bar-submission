"""Finance AI Chat — routed through the MAS supervisor agent endpoint.

The supervisor endpoint (set via MAS_ENDPOINT_NAME) uses the Responses API format:
  - Request:  { "input": [{role, content}], "max_tokens": N }
  - Response: { "output": [ {type, role, content: [{type, text}]} ] }

The final answer is in the last "message" output item. Intermediate items
contain the Genie tool call and raw table data — we surface the final
formatted answer which includes the cleaned-up markdown table + insights.

Session history is persisted to Lakebase (falls back to in-memory).
"""
import asyncio
import json
import os
import re
import aiohttp
from backend import db
from backend.config import get_workspace_host, get_token, CATALOG, SCHEMA

MAS_ENDPOINT = os.environ.get("MAS_ENDPOINT_NAME", "")
AGENT_ENDPOINT = MAS_ENDPOINT or "finance-sql-agent (Claude + SQL fallback)"
FMAPI_MODEL = MAS_ENDPOINT     # backwards-compat

# Foundation model used by the built-in fallback agent (no MAS endpoint required).
FOUNDATION_MODEL = os.environ.get("FMAPI_MODEL", "databricks-claude-sonnet-4-5")

# Compact schema of the governed gold tables the fallback agent may query.
# Catalog/schema are bound on the SQL request, so tables are referenced by bare name.
GOLD_SCHEMA = """
gold_fact_invoices  -- AP / Procure-to-Pay invoices (one row per invoice)
  invoice_id, invoice_number, po_id, vendor_id, vendor_name, vendor_category,
  invoice_date, due_date, payment_date, invoice_amount, tax_amount, invoice_total_inr,
  paid_amount_inr, invoice_status, match_status (THREE_WAY_MATCHED|TWO_WAY_MATCHED|AMOUNT_MISMATCH|NO_PO_REFERENCE|PENDING_REVIEW),
  has_po_ref, has_grn, is_overdue, aging_days, aging_bucket, days_to_pay, payment_on_time,
  days_outstanding, invoice_year, invoice_month, invoice_quarter, data_source
gold_dim_vendor  -- vendor master + rollups
  vendor_id, vendor_name, vendor_category, payment_terms, gstin, total_invoices,
  total_spend_inr, avg_invoice_amount_inr, three_way_matched_invoices, amount_mismatch_invoices,
  total_paid_amount_inr, match_compliance_pct
gold_fact_payments  -- AP payments
  payment_id, invoice_id, vendor_id, vendor_name, payment_date, due_date, payment_amount_inr,
  invoice_total_inr, payment_method, payment_status, days_to_pay, early_late_days, payment_timing
gold_fact_collections  -- AR / Order-to-Cash invoices & collections
  o2c_invoice_id, invoice_number, customer_id, customer_name, segment, region, invoice_date,
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
gold_recon_subledger_vs_gl  -- subledger vs GL reconciliation
  account_code, account_name, balance_type, subledger_amount, gl_amount, delta, tied
""".strip()


def _token(user_token: str | None = None) -> str:
    sp_token = get_token()
    if sp_token:
        return sp_token
    if user_token:
        return user_token
    return ""


def _extract_answer(output: list) -> str:
    """
    Extract the final formatted answer from the MAS output array.

    The output array looks like:
      [0] message  — "I'll query the system..."
      [1] function_call — Genie tool call
      [2] message  — raw <name> routing tag (skip)
      [3] message  — raw Genie SQL result table (skip)
      [4] message  — raw <name> routing tag (skip)
      [5] message  — final formatted answer  ← this is what we want

    Strategy: take the LAST message item whose text is NOT just a <name> tag.
    """
    candidates = []
    for item in output:
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            text = c.get("text", "").strip()
            if not text:
                continue
            # Skip bare routing tags like <name>...</name>
            if text.startswith("<name>") and text.endswith("</name>"):
                continue
            candidates.append(text)

    if not candidates:
        return ""

    # The last candidate is the final formatted answer
    return candidates[-1]


async def _fmapi_chat(messages: list[dict], user_token: str | None = None,
                      max_tokens: int = 1024, temperature: float = 0.0) -> str:
    """Single-shot call to the Claude foundation model (OpenAI-compatible invocations)."""
    token = _token(user_token)
    url = f"{get_workspace_host()}/serving-endpoints/{FOUNDATION_MODEL}/invocations"
    payload = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=90)) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"FMAPI HTTP {resp.status}: {body[:300]}")
    d = json.loads(body)
    msg = d.get("choices", [{}])[0].get("message", {})
    content = msg.get("content", "")
    if isinstance(content, list):  # some models return content parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return (content or "").strip()


def _clean_sql(text: str) -> str:
    """Strip markdown fences / prose and keep a single SELECT statement."""
    m = re.search(r"```(?:sql)?\s*(.+?)```", text, re.DOTALL | re.IGNORECASE)
    sql = (m.group(1) if m else text).strip().rstrip(";").strip()
    # Keep only from the first SELECT/WITH (defensive against leading prose)
    m2 = re.search(r"(?is)\b(with|select)\b", sql)
    if m2:
        sql = sql[m2.start():].strip()
    return sql


async def stream_sql_agent(question: str, active_tab: str = "P2P",
                           user_token: str | None = None, history: list[dict] | None = None):
    """Built-in finance agent: Claude turns the question into SQL over the gold
    tables, runs it on the warehouse, and Claude narrates the result. Used when no
    MAS/AgentBricks endpoint is configured. Yields the same event dicts as the MAS path."""
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
            "to answer the user's question. You MUST reference every table fully-qualified as "
            f"`{CATALOG}`.`{SCHEMA}`.<table_name> (e.g. `{CATALOG}`.`{SCHEMA}`.gold_fact_invoices). "
            "Always add a sensible LIMIT (<=100). Use current_date() for relative dates. "
            "For 'at risk of late payment' / 'overdue' / 'due soon', return UNPAID invoices "
            "(invoice_status <> 'PAID') that are already overdue (is_overdue = true) OR due within the "
            "next 7 days (due_date BETWEEN current_date() AND current_date() + INTERVAL 7 DAYS), ordered "
            "by due_date ascending; select invoice_number, vendor_name, invoice_total_inr, due_date, "
            "days_outstanding, invoice_status, match_status. "
            f"The user is on the {domain} tab. Output ONLY the SQL, no prose, no comments.\n\n"
            f"GOLD TABLES (all in `{CATALOG}`.`{SCHEMA}`):\n{GOLD_SCHEMA}"},
        {"role": "user", "content": question + ctx},
    ]

    try:
        raw_sql = await _fmapi_chat(sql_prompt, user_token=user_token, max_tokens=700)
        sql = _clean_sql(raw_sql)
        if not re.match(r"(?is)^\s*(with|select)\b", sql):
            yield {"type": "error", "message": "Could not generate a valid query for that question."}
            return
    except Exception as e:
        yield {"type": "error", "message": f"Agent (SQL generation) failed: {e}"}
        return

    try:
        rows = await asyncio.to_thread(db.query, sql)
    except Exception as e:
        # One retry: let Claude repair the query given the error.
        try:
            fix = await _fmapi_chat(sql_prompt + [
                {"role": "assistant", "content": sql},
                {"role": "user", "content": f"That query failed with: {str(e)[:300]}. Return a corrected SQL SELECT only."},
            ], user_token=user_token, max_tokens=700)
            sql = _clean_sql(fix)
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
    chunk_size = 40
    for i in range(0, len(answer), chunk_size):
        yield {"type": "chunk", "text": answer[i:i + chunk_size]}
        await asyncio.sleep(0.01)
    yield {"type": "done", "response_id": None, "tool": "finance-sql-agent"}


async def stream_mas_agent(
    messages: list[dict],
    user_token: str | None = None,
    previous_response_id: str | None = None,
    active_tab: str = "P2P",
):
    """
    Route the question to the MAS supervisor when one is configured; otherwise fall
    back to the built-in Claude + SQL agent over the gold tables.

    Call the MAS supervisor and yield the answer as streaming chunks.

    The MAS endpoint does not support SSE streaming, so we call it once
    and yield the answer in ~50-char chunks to keep the streaming UX.

    Yields dicts:
      {"type": "chunk",  "text": "..."}
      {"type": "done",   "response_id": None, "tool": None}
      {"type": "error",  "message": "..."}
    """
    # No MAS / AgentBricks endpoint configured → built-in Claude + SQL agent.
    if not MAS_ENDPOINT:
        question = next((m.get("content", "") for m in reversed(messages)
                         if m.get("role") == "user"), "")
        history = messages[:-1] if messages else []
        async for ev in stream_sql_agent(question, active_tab=active_tab,
                                          user_token=user_token, history=history):
            yield ev
        return

    token = _token(user_token)
    host = get_workspace_host()
    url = f"{host}/serving-endpoints/{MAS_ENDPOINT}/invocations"

    payload = {
        "input": list(messages),
        "max_tokens": 2048,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    yield {"type": "error", "message": f"HTTP {resp.status}: {error_text[:300]}"}
                    return

                body = await resp.text()

        d = json.loads(body)
        output = d.get("output", [])
        answer = _extract_answer(output)

        if not answer:
            yield {"type": "error", "message": "No answer returned from supervisor."}
            return

        # Stream the answer in chunks to preserve the typing-effect UX
        chunk_size = 40
        for i in range(0, len(answer), chunk_size):
            yield {"type": "chunk", "text": answer[i:i + chunk_size]}
            await asyncio.sleep(0.01)

        yield {"type": "done", "response_id": None, "tool": None}

    except Exception as e:
        yield {"type": "error", "message": str(e)}


async def handle_chat(
    question: str,
    active_tab: str = "P2P",
    user_token: str | None = None,
    history: list[dict] | None = None,
    previous_response_id: str | None = None,
) -> dict:
    """Send a question to the MAS supervisor and return a structured result."""
    result = {
        "question": question,
        "domain": active_tab,
        "routing": {
            "domain": "MAS Supervisor",
            "explanation": f"Routed via {MAS_ENDPOINT}",
        },
        "genie_response": None,
        "sql": None,
        "data": None,
        "answer": None,
        "error": None,
        "agent": MAS_ENDPOINT,
        "previous_response_id": None,
    }

    messages = list(history[-20:]) if history else []
    messages.append({"role": "user", "content": question})

    full_answer = ""
    async for event in stream_mas_agent(messages, user_token=user_token):
        if event["type"] == "chunk":
            full_answer += event["text"]
        elif event["type"] == "error":
            result["error"] = event["message"]
            return result

    result["answer"] = full_answer.strip() or "No answer returned. Please try again."
    return result
