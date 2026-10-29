#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Idempotent teardown: remove everything setup created, with no orphans.
#   1. Drops the demo Unity Catalog catalog (schemas, tables, volumes) via the
#      fna_teardown_job — run BEFORE destroy so the job still exists.
#   2. Destroys all bundle-managed resources (DLT pipeline, jobs, app).
#
# Usage (host comes from DATABRICKS_HOST or a -p profile — never hardcoded):
#   export DATABRICKS_HOST=https://<ws>.cloud.databricks.com   # or pass -p <profile>
#   ./setup/teardown.sh
#   BUNDLE_TARGET=dev ./setup/teardown.sh -p <profile>
#
# Note: the Lakebase instance, Genie space, and MAS endpoint are provisioned
# manually (MANUAL_DEPLOY.md) and are removed there, not by this script.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="${BUNDLE_TARGET:-dev}"
cd "$REPO_ROOT"

echo "==> [1/2] Dropping demo catalog (UC data the bundle does not own)"
databricks bundle run fna_teardown_job -t "$TARGET" "$@" || \
  echo "    (teardown job not available — catalog may already be gone)"

echo "==> [2/2] Destroying bundle-managed resources (pipeline, jobs, app)"
databricks bundle destroy -t "$TARGET" --auto-approve "$@"

echo ""
echo "✅ Teardown complete. Re-run ./setup/setup.sh to rebuild from zero."
