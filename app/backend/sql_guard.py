"""Guard for LLM-generated SQL (chat fallback agent).

The prompt asks the model for one read-only query, but the prompt is not a
control. Every generated statement is parsed with sqlglot and rejected unless:
  - it is exactly ONE statement, and that statement is a SELECT (optionally WITH / UNION)
  - it contains no DDL / DML / command nodes anywhere in the tree
  - every table it reads is on the allow-list and lives in the configured catalog.schema
  - its LIMIT is at most MAX_LIMIT (added when missing, clamped when larger)
The guarded SQL then runs with the signed-in user's token, so UC grants, row
filters and column masks still apply on top of this check.
"""
import re
import sqlglot
from sqlglot import exp

MAX_LIMIT = 100

# Tables the chat agent may read (bare names, matched case-insensitively).
_ALLOWED_PATTERNS = (
    re.compile(r"^gold_[a-z0-9_]+$"),            # gold_fact_*, gold_dim_*, gold_recon_*, gold_ai_extraction_eval
    re.compile(r"^silver_invoice_exceptions$"),
)

_FORBIDDEN_NODES = tuple(
    getattr(exp, name) for name in (
        "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "AlterTable",
        "Command", "TruncateTable", "Grant", "Revoke", "Use", "Set", "Copy", "LoadData",
        "Cache", "Uncache", "Refresh", "Analyze", "Describe", "Pragma",
    ) if hasattr(exp, name)
)


class SqlGuardError(ValueError):
    """Raised when generated SQL fails the read-only / allow-list policy."""


def is_allowed_table(name: str) -> bool:
    n = (name or "").lower()
    return any(p.match(n) for p in _ALLOWED_PATTERNS)


def guard_sql(sql: str, catalog: str, schema: str, max_limit: int = MAX_LIMIT) -> str:
    """Validate `sql` and return a normalised, LIMIT-enforced Databricks SQL string."""
    text = (sql or "").strip()
    if not text:
        raise SqlGuardError("empty query")
    try:
        statements = [s for s in sqlglot.parse(text, read="databricks") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise SqlGuardError(f"unparseable SQL: {str(e)[:200]}") from e

    if len(statements) != 1:
        raise SqlGuardError(f"exactly one statement allowed, got {len(statements)}")
    tree = statements[0]

    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise SqlGuardError(f"only SELECT / WITH queries are allowed (got {type(tree).__name__})")
    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise SqlGuardError(f"forbidden operation: {type(node).__name__}")

    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    tables = list(tree.find_all(exp.Table))
    if not tables:
        raise SqlGuardError("query must read from at least one governed table")
    for t in tables:
        name = t.name
        if not t.args.get("db") and name.lower() in cte_names:
            continue
        if not is_allowed_table(name):
            raise SqlGuardError(f"table not on allow-list: {name}")
        db = t.args.get("db")
        cat = t.args.get("catalog")
        if db is not None and db.name.lower() != schema.lower():
            raise SqlGuardError(f"table {name} must be in schema {schema}, got {db.name}")
        if cat is not None and cat.name.lower() != catalog.lower():
            raise SqlGuardError(f"table {name} must be in catalog {catalog}, got {cat.name}")
        # Fully qualify so execution never depends on the session's default schema.
        t.set("db", exp.to_identifier(schema))
        t.set("catalog", exp.to_identifier(catalog))

    limit = tree.args.get("limit")
    current = None
    if limit is not None:
        lit = limit.expression if isinstance(limit, exp.Limit) else limit
        if isinstance(lit, exp.Literal) and lit.is_int:
            current = int(lit.this)
        else:
            current = None  # non-literal LIMIT → replace with the cap
    if current is None or current > max_limit:
        tree = tree.limit(max_limit, copy=False) if hasattr(tree, "limit") else tree
        if tree.args.get("limit") is None:
            raise SqlGuardError("could not enforce LIMIT")

    return tree.sql(dialect="databricks")
