# F5 — Every layer wired and deployed by the bundle

## Bundle resources (`databricks bundle summary -t dev`)

```
Name: cfo-fna-ops-control-tower
Target: dev
Workspace:
  User: akash.s@databricks.com
  Path: /Workspace/Users/akash.s@databricks.com/.bundle/cfo-fna-ops-control-tower/dev
Resources:
  Apps:
    fna_control_tower_app:
      Name: cfo-fna-control-tower-dev
      URL:  (not deployed)
  Database instances:
    fna_lakebase:
      Name: fna-control-tower-db
      URL:  https://fevm-akash-fevm-ts.cloud.databricks.com/compute/database-instances/fna-control-tower-db?w=<workspace-id>
  Jobs:
    fna_lakebase_writeback_job:
      Name: [dev akash_s] cfo-fna-control-tower-lakebase-writeback-dev
      URL:  https://fevm-akash-fevm-ts.cloud.databricks.com/jobs/1001351890163343?w=<workspace-id>
    fna_setup_job:
      Name: [dev akash_s] cfo-fna-control-tower-setup-dev
      URL:  https://fevm-akash-fevm-ts.cloud.databricks.com/jobs/696265687437193?w=<workspace-id>
    fna_teardown_job:
      Name: [dev akash_s] cfo-fna-control-tower-teardown-dev
      URL:  https://fevm-akash-fevm-ts.cloud.databricks.com/jobs/563744222402192?w=<workspace-id>
  Pipelines:
    fna_dlt_pipeline:
      Name: [dev akash_s] cfo-fna-control-tower-dlt-dev
      URL:  https://fevm-akash-fevm-ts.cloud.databricks.com/pipelines/b6b62b82-aef9-48fc-b74d-c1ca9d868a92?w=<workspace-id>
```

The app (`cfo-fna-control-tower-dev`, deployment `01f1d39467ed1d5bbf01c08784c9f321`) is live at
`https://cfo-fna-control-tower-dev-7474646051057767.aws.databricksapps.com`; the summary prints "not deployed" for
the app URL, but `databricks apps get` reports the active deployment. App resources: `sql-warehouse`,
`claude-endpoint`, `finance-ops-db` (Lakebase). User API scopes: `sql`, `dashboards.genie`,
`serving.serving-endpoints`, `files.files`. The Genie space `01f1d38f62131010a21422b74b92e9e6` is created by the
setup job's `genie_space` task and passed to the app by `setup/setup.sh`.

## App status (`GET /api/debug/status`, live)

```json
{
  "demo_mode": false,
  "auth_mode": "obo",
  "db.live": true,
  "db.warehouse_id": "87c76aa3893e6472",
  "lakebase.connected": true,
  "lakebase.queue_table": "finance_ops_control_tower.ap_exception_queue",
  "genie": {
    "configured": true,
    "space_id": "01f1d38f62131010a21422b74b92e9e6",
    "mas_endpoint": null,
    "chat_route": "genie"
  }
}
```

`demo_mode` is false, reads run on behalf of the signed-in user (`auth_mode: obo`), Lakebase is connected and the chat
routes to the Genie space.

## Loop closed: Gold → Lakebase → app → Lakebase → Unity Catalog

1. `gold_ap_exception_queue` (pipeline) is synced to Postgres `finance_ops_control_tower.ap_exception_queue`
   (407 rows) — `lakebase.md`.
2. The app reads the queue from Lakebase (`GET /api/ap/exception-queue` returns `"source": "lakebase"`) —
   `app_api_responses.md`.
3. A rejection of INV000198 made through the app is in Postgres `fna_app.ap_approvals` and, after the write-back job,
   in Unity Catalog `ops_ap_approvals` — `lakebase.md`.
4. Genie answers through the app chat (`POST /api/chat`, route `genie`) and directly through the Conversation API
   (6 of 6 questions completed) — `genie_transcripts.md`.

## Agent Bricks supervisor

Not created. The chat routes to the Genie Conversation API; `--var mas_endpoint_name=<endpoint>` switches it to a
supervisor if one is added.
