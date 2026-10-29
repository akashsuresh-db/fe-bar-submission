"""Collect Genie transcripts and live app API responses into evidence/*.md.

Usage:
  python evidence/collect_genie_app.py -p <profile> --space-id <genie_space_id> --app-url <https://...> [--only genie,app]

Genie questions go through the Genie Conversation API as the CLI user. App calls use a Bearer token from
`databricks auth token`; the token is never written to disk.
"""
import argparse
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent

QUESTIONS = [
    ("AP lead", "What is our touchless invoice rate, and how many invoices are release-blocked?"),
    ("AP lead", "Which invoices were blocked because the PDF disagrees with the ERP?"),
    ("Controller", "Do AR and AP tie to the general ledger, and what explains any difference?"),
    ("Collections manager", "Which five customers have the largest overdue receivables?"),
    ("CFO", "Give me a working capital snapshot: cash, receivables and payables from the latest trial balance."),
    ("Architect", "How accurate is the AI invoice extraction?"),
]


def cli(profile, *args):
    out = subprocess.run(["databricks", *args, "-p", profile, "-o", "json"], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:400])
    return json.loads(out.stdout or "{}")


def ask(profile, space, question):
    msg = cli(profile, "api", "post", f"/api/2.0/genie/spaces/{space}/start-conversation",
              "--json", json.dumps({"content": question}))
    conv, mid = msg["conversation_id"], msg["message_id"]
    for _ in range(90):
        m = cli(profile, "api", "get", f"/api/2.0/genie/spaces/{space}/conversations/{conv}/messages/{mid}")
        if m.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(3)
    text, sql, table = [], None, None
    for att in m.get("attachments") or []:
        if att.get("text"):
            text.append(att["text"].get("content", ""))
        if att.get("query"):
            sql = att["query"].get("query")
            if att["query"].get("description"):
                text.append(att["query"]["description"])
            res = cli(profile, "api", "get",
                      f"/api/2.0/genie/spaces/{space}/conversations/{conv}/messages/{mid}/attachments/{att['attachment_id']}/query-result")
            stmt = res.get("statement_response", {})
            cols = [c["name"] for c in stmt.get("manifest", {}).get("schema", {}).get("columns", [])]
            rows = stmt.get("result", {}).get("data_array", []) or []
            table = (cols, rows)
    return m.get("status"), "\n".join(t for t in text if t), sql, table


def md_table(cols, rows, limit=15):
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join("" if v is None else str(v)[:80] for v in r) + " |" for r in rows[:limit]]
    return "\n".join(out)


def http(url, token, method="GET", body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--profile", required=True)
    ap.add_argument("--space-id", default="")
    ap.add_argument("--app-url", default="")
    ap.add_argument("--only", default="genie,app")
    a = ap.parse_args()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    only = set(a.only.split(","))

    if "genie" in only and a.space_id:
        parts = [f"# Genie transcripts\n\n_Collected {ts} through the Genie Conversation API, space `{a.space_id}`._\n"]
        for i, (persona, q) in enumerate(QUESTIONS, 1):
            status, text, sql, table = ask(a.profile, a.space_id, q)
            parts.append(f"## {i}. {persona}: {q}\n\n**Status:** {status}\n\n**Answer:** {text or '(table only)'}\n")
            if sql:
                parts.append(f"```sql\n{sql}\n```\n")
            if table and table[0]:
                parts.append(md_table(*table) + "\n")
        (HERE / "genie_transcripts.md").write_text("\n".join(parts))
        print("wrote evidence/genie_transcripts.md")

    if "app" in only and a.app_url:
        token = cli(a.profile, "auth", "token")["access_token"]
        base = a.app_url.rstrip("/")
        calls = [("GET", "/api/health", None), ("GET", "/api/debug/status", None),
                 ("GET", "/api/metrics/p2p", None), ("GET", "/api/metrics/o2c", None),
                 ("GET", "/api/metrics/r2r", None), ("GET", "/api/recon", None),
                 ("GET", "/api/verify-invoice/INV000033", None), ("GET", "/api/summary/P2P", None)]
        parts = [f"# App API responses\n\n_Collected {ts} from `{base}` with a Bearer token (masked)._\n"]
        for method, path, body in calls:
            code, text = http(base + path, token, method, body)
            try:
                text = json.dumps(json.loads(text), indent=2)
            except Exception:
                pass
            parts.append(f"## `{method} {path}` → {code}\n\n```json\n{text[:6000]}\n```\n")
        (HERE / "app_api_responses.md").write_text("\n".join(parts))
        print("wrote evidence/app_api_responses.md")


if __name__ == "__main__":
    main()
