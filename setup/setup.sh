#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Idempotent setup: deploy the Asset Bundle and build the demo from zero.
# Safe to re-run — notebooks use CREATE ... IF NOT EXISTS / OVERWRITE throughout.
#
# Usage (host comes from DATABRICKS_HOST or a -p profile — never hardcoded):
#   export DATABRICKS_HOST=https://<ws>.cloud.databricks.com   # or pass -p <profile>
#   ./setup/setup.sh --var="warehouse_id=<id>"
#   BUNDLE_TARGET=dev ./setup/setup.sh -p <profile> --var="catalog=my_catalog"
#
# Prereqs (see MANUAL_DEPLOY.md): a Lakebase instance named per var.lakebase_instance_name
# and (for chat/Genie) a Genie space + MAS endpoint. The core data + app work without them.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="${BUNDLE_TARGET:-dev}"
cd "$REPO_ROOT"

echo "==> [1/4] Validating bundle (target: $TARGET)"
databricks bundle validate -t "$TARGET" "$@"

echo "==> [2/4] Deploying bundle resources (DLT pipeline, jobs, app)"
databricks bundle deploy -t "$TARGET" "$@"

echo "==> [3/4] Running setup job (data gen -> DLT -> gold -> AI extraction)"
databricks bundle run fna_setup_job -t "$TARGET" "$@"

echo "==> [4/4] Deploying/starting the app"
databricks bundle run fna_control_tower_app -t "$TARGET" "$@" || \
  echo "    (app run skipped — ensure warehouse_id and Lakebase instance are set)"

echo ""
echo "✅ Setup complete. Inspect resources with: databricks bundle summary -t $TARGET"
