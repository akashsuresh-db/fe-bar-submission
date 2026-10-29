# Manual Deploy — components not covered by the Asset Bundle

Everything deployable ships in the Databricks Asset Bundle (`databricks.yml` +
`resources/`): the DLT pipeline, the setup/teardown jobs, and the Databricks App.

The components below **cannot** be created by a bundle today (no DAB resource type,
or they depend on account/region features). Provision them manually, then feed the
resulting IDs back to the app as bundle variables / app env vars.

---

## 1. Lakebase (managed Postgres) instance

Backs the app's operational state (session memory, approvals, call logs). The app
attaches it as a `database` resource (`resources/apps.yml`), but the **instance itself**
is created out of band.

**Create** (UI: *Compute → Database instances → Create*, or CLI):
```bash
databricks database create-database-instance \
  --json '{"name": "finance-ops-db", "capacity": "CU_1"}'
```
Then create the app database inside it (default name `finance_ops_app`).

**Wire it up:** pass the instance name to the bundle if you changed it:
```bash
./setup/setup.sh --var="lakebase_instance_name=finance-ops-db"
```
`PGHOST` / `PGUSER` / `PGPASSWORD` are injected into the app automatically by the
attached `database` resource. If the instance is absent the app runs in in-memory demo mode.

---

## 2. Genie space

Natural-language analytics over the gold tables. Genie spaces have no DAB resource type.

**Create** using the notebooks in `notebooks/` (parameterized — pass `catalog`, `schema`,
`warehouse_id` as widgets/job params):
- `06_Genie_Space_Setup.py` — table descriptions + sample questions
- `07_Create_Genie_Space.py` — creates the space via the SDK
- `08_Configure_Genie_Space.py` — adds instructions + curated questions (pass `space_id`)

**Wire it up:** set the resulting space ID on the app:
```
GENIE_SPACE_ID = <your-genie-space-id>   # app env var in app/app.yaml (or app settings)
```

---

## 3. MAS / AgentBricks supervisor endpoint

The multi-agent chat routes through a Multi-Agent Supervisor (AgentBricks) serving
endpoint. AgentBricks / Knowledge Assistant endpoints are not DAB-deployable.

**Create** the supervisor in AgentBricks (UI), attach the Genie space above as a tool,
and note the serving-endpoint name.

**Wire it up:** set the endpoint name on the app:
```
MAS_ENDPOINT_NAME = <your-mas-endpoint-name>   # app env var in app/app.yaml
```
The app's `claude-endpoint` (foundation model) resource IS bundle-managed; only the
custom MAS endpoint is manual.

---

## 4. Vector Search

Not used by this demo. If you add semantic search later, create the Vector Search
endpoint + index manually (no DAB resource type) and document it here.

---

## Post-deploy checklist

| Manual asset | Feeds | App variable |
|---|---|---|
| Lakebase instance | `resources/apps.yml` database resource | `lakebase_instance_name` (bundle var) |
| SQL warehouse (existing) | `resources/apps.yml` sql_warehouse | `warehouse_id` (bundle var) |
| Genie space | app runtime | `GENIE_SPACE_ID` (app env) |
| MAS endpoint | app runtime | `MAS_ENDPOINT_NAME` (app env) |
