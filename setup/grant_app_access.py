"""Grant the app's service principal least-privilege access (used by setup.sh).

The app reads as the signed-in user (on-behalf-of-user authorization). Its service principal still needs
read access for background work without a user context (the SSE replay streams) and Genie access for the
service-principal fallback. It is NOT added to finance_controllers, so it sees masked bank details.
"""
import argparse
import json
import subprocess
import sys
import time


def cli(*args, profile=None):
    cmd = ["databricks", *args, "-o", "json"] + (["-p", profile] if profile else [])
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}: {out.stderr.strip()}")
    return json.loads(out.stdout or "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="dev")
    ap.add_argument("--genie-space-id", default="")
    ap.add_argument("-p", "--profile")
    ap.add_argument("--var", action="append", default=[])
    a, _ = ap.parse_known_args()
    vars_ = dict(v.split("=", 1) for v in a.var)

    bundle_args = ["bundle", "summary", "-t", a.target] + [f"--var={v}" for v in a.var]
    summary = cli(*bundle_args, profile=a.profile)
    catalog = summary["variables"]["catalog"]["value"]
    schema = summary["variables"]["schema"]["value"]
    warehouse = vars_.get("warehouse_id") or summary["variables"]["warehouse_id"]["value"]
    app_name = summary["resources"]["apps"]["fna_control_tower_app"]["name"]
    sp = cli("apps", "get", app_name, profile=a.profile)["service_principal_client_id"]

    statements = [
        f"GRANT USE CATALOG ON CATALOG {catalog} TO `{sp}`",
        f"GRANT USE SCHEMA ON SCHEMA {catalog}.{schema} TO `{sp}`",
        f"GRANT SELECT ON SCHEMA {catalog}.{schema} TO `{sp}`",
        f"GRANT EXECUTE ON SCHEMA {catalog}.{schema} TO `{sp}`",
        f"GRANT READ VOLUME ON VOLUME {catalog}.{schema}.raw_invoices TO `{sp}`",
    ]
    for stmt in statements:
        body = {"warehouse_id": warehouse, "statement": stmt, "wait_timeout": "50s"}
        res = cli("api", "post", "/api/2.0/sql/statements", "--json", json.dumps(body), profile=a.profile)
        while res.get("status", {}).get("state") in ("PENDING", "RUNNING"):
            time.sleep(2)
            res = cli("api", "get", f"/api/2.0/sql/statements/{res['statement_id']}", profile=a.profile)
        state = res.get("status", {}).get("state")
        print(f"    {state:<9} {stmt}")
        if state != "SUCCEEDED":
            sys.exit(f"grant failed: {res.get('status', {}).get('error')}")

    if a.genie_space_id:
        acl = {"access_control_list": [{"service_principal_name": sp, "permission_level": "CAN_RUN"}]}
        cli("api", "patch", f"/api/2.0/permissions/genie/{a.genie_space_id}", "--json", json.dumps(acl), profile=a.profile)
        print(f"    CAN_RUN on Genie space {a.genie_space_id} -> {sp}")


if __name__ == "__main__":
    main()
