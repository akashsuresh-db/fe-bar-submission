"""Configuration for the Finance Operations App."""
import os
import contextvars

IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID", "")
CATALOG = os.environ.get("DATABRICKS_CATALOG", "fna_control_tower_catalog")
SCHEMA = os.environ.get("DATABRICKS_SCHEMA", "finance_and_accounting")

# Demo data is served ONLY when explicitly requested. Any other failure surfaces
# as a typed error + UI banner instead of invented numbers.
DEMO_MODE = os.environ.get("DEMO_MODE", "false").strip().lower() in ("1", "true", "yes")

# Lakebase synced table (Gold → Postgres) that backs the AP exception queue.
# The synced table lands in a Postgres schema named after the UC schema.
LAKEBASE_QUEUE_TABLE = os.environ.get("LAKEBASE_QUEUE_TABLE", f"{SCHEMA}.ap_exception_queue")

FMAPI_MODEL = "databricks-claude-sonnet-4-5"

# ─── On-behalf-of-user token ─────────────────────────────────
# Databricks Apps forwards the signed-in user's token in x-forwarded-access-token
# (user authorization). A pure-ASGI middleware in main.py stores it here per
# request so warehouse reads run AS THE USER and Unity Catalog row filters /
# column masks apply. Code paths without a request (startup probe) fall back to
# the app service principal.
_user_token: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_token", default=None)


def set_user_token(token: str | None):
    return _user_token.set(token or None)


def reset_user_token(tok) -> None:
    _user_token.reset(tok)


def current_user_token() -> str | None:
    return _user_token.get()


def auth_mode() -> str:
    """'obo' when the current request carries a user token, else 'sp'."""
    return "obo" if current_user_token() else "sp"


def get_workspace_host() -> str:
    """Get workspace host URL with https:// prefix."""
    host = os.environ.get("DATABRICKS_HOST", "")
    if host and not host.startswith("http"):
        host = f"https://{host}"
    if not host:
        # Last-resort fallback for local dev; override with DATABRICKS_HOST
        host = os.environ.get("DATABRICKS_WORKSPACE_URL", "")
    return host.rstrip("/")


def get_token() -> str:
    """Get the app service-principal token - works in Databricks Apps and locally."""
    # First try explicit token
    token = os.environ.get("DATABRICKS_TOKEN", "")
    if token:
        return token

    # Try Databricks SDK (works for service principal and local dev)
    try:
        from databricks.sdk import WorkspaceClient

        if IS_DATABRICKS_APP:
            w = WorkspaceClient()
        else:
            profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
            w = WorkspaceClient(profile=profile)

        if w.config.token:
            return w.config.token

        headers = w.config.authenticate()
        if headers and "Authorization" in headers:
            return headers["Authorization"].replace("Bearer ", "")
    except Exception as e:
        print(f"SDK auth failed: {e}")

    return ""


def get_read_token() -> str:
    """Token for data reads: the signed-in user's token (OBO) when present, else the SP."""
    return current_user_token() or get_token()


def full_table(table: str) -> str:
    """Return fully qualified table name."""
    return f"`{CATALOG}`.`{SCHEMA}`.`{table}`"
