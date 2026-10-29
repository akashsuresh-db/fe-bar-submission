# Deployment — what is automated and what is not

`setup/setup.sh` builds the whole demo from an empty schema. Nothing is created by hand.

| Component | How it is created | Where |
|---|---|---|
| Lakeflow declarative pipeline (bronze → silver → gold, AI extraction) | Bundle | `resources/pipelines.yml` |
| Setup, Lakebase write-back and teardown jobs | Bundle | `resources/jobs.yml` |
| Lakebase instance | Bundle (`database_instances`) | `resources/lakebase.yml` |
| Databricks App with warehouse, model endpoint and Lakebase resources, on-behalf-of-user scopes | Bundle | `resources/apps.yml` |
| Groups, entity map, row filter, column masks, tags, grants | Setup job, `00d_Governance` | `notebooks/00d_Governance.py` |
| Lakebase synced table `ap_exception_queue` and UC write-back tables `ops_*` | Setup job, `10_Lakebase_Sync` | `notebooks/10_Lakebase_Sync.py` |
| Genie space | Setup job, `06_Genie_Space` (Genie validates that its tables exist, so it is created after the pipeline) | `notebooks/06_Genie_Space.py` |
| App service-principal grants and Genie `CAN_RUN` | `setup.sh` step 4 | `setup/grant_app_access.py` |

## Prerequisites

- A workspace with Unity Catalog, serverless compute, Lakebase and Databricks Apps (with user authorization) enabled.
- An existing SQL warehouse (`--var warehouse_id=<id>`).
- A catalog you can create schemas in (`--var catalog=<catalog>`). `00a_Reset_Schema` creates the catalog only if it does not exist.
- Workspace admin rights, so `00d_Governance` can create the workspace-local groups.

## Run

```bash
./setup/setup.sh -p <profile> --var="catalog=<catalog>" --var="schema=<schema>" --var="warehouse_id=<id>"
```

Re-running is safe: the job clears the landing volumes, re-lands deterministic data and runs the pipeline with a
full refresh.

## Optional

- **Agent Bricks supervisor.** Create a supervisor agent with the Genie space as a tool and pass
  `--var="mas_endpoint_name=<endpoint>"`. Without it, the app chat sends questions to the Genie Conversation API.
- **Lakebase write-back cadence.** Unpause `cfo-fna-control-tower-lakebase-writeback-<target>` to copy app writes to
  Unity Catalog every 30 minutes; the setup job copies them once per run.

## Known platform constraints (and the substitute used)

| Constraint | Substitute |
|---|---|
| Registering the Lakebase database as a UC catalog needs `CREATE CATALOG` on the metastore | `10_Lakebase_Sync` copies `ap_approvals`, `ar_call_logs` and `chat_history` into `ops_*` Delta tables |
| Account groups cannot be created from an FEVM workspace | Workspace-local groups with `is_member()` in the row filter and masks |
| The app's database resource must exist at first deploy | The app uses the instance's default database `databricks_postgres` |

## Teardown

```bash
./setup/teardown.sh -p <profile> --var="catalog=<catalog>" --var="schema=<schema>" --var="warehouse_id=<id>"
```

Drops the demo schema (not the catalog), then destroys the bundle resources.
