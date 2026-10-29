#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Idempotent setup: deploy the bundle and build the demo from zero. Safe to re-run.
#
# Usage (host comes from DATABRICKS_HOST or a -p profile — never hardcoded):
#   ./setup/setup.sh -p <profile> --var="catalog=<catalog>" --var="schema=<schema>" --var="warehouse_id=<id>"
#
# Steps:
#   1. validate + deploy (pipeline, jobs, Lakebase instance, app)
#   2. run the setup job (land data -> governance -> pipeline -> AI eval -> Lakebase sync -> Genie space)
#   3. read the Genie space id from the genie_space task output and redeploy the app with it
#   4. grant the app's service principal read access and Genie access, then start the app
# Manual: nothing. Optional: an Agent Bricks supervisor (--var="mas_endpoint_name=<endpoint>").
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="${BUNDLE_TARGET:-dev}"
cd "$REPO_ROOT"

# Split "-p <profile>" from the --var flags so it can be reused for non-bundle CLI calls
PROFILE_ARGS=()
ARGS=("$@")
for ((i = 0; i < ${#ARGS[@]}; i++)); do
  if [[ "${ARGS[$i]}" == "-p" || "${ARGS[$i]}" == "--profile" ]]; then PROFILE_ARGS=(-p "${ARGS[$((i + 1))]}"); fi
done

echo "==> [1/4] Validating and deploying the bundle (target: $TARGET)"
databricks bundle validate -t "$TARGET" "$@"
databricks bundle deploy -t "$TARGET" "$@"

echo "==> [2/4] Running the setup job"
RUN_JSON=$(databricks bundle run fna_setup_job -t "$TARGET" "$@" -o json)
RUN_ID=$(echo "$RUN_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['run_id'])")
echo "    setup run $RUN_ID finished"

echo "==> [3/4] Wiring the Genie space into the app"
GENIE_TASK_RUN=$(databricks jobs get-run "$RUN_ID" "${PROFILE_ARGS[@]}" -o json | python3 -c \
  "import json,sys; print([t['run_id'] for t in json.load(sys.stdin)['tasks'] if t['task_key']=='genie_space'][0])")
GENIE_SPACE_ID=$(databricks jobs get-run-output "$GENIE_TASK_RUN" "${PROFILE_ARGS[@]}" -o json | python3 -c \
  "import json,sys; print(json.loads(json.load(sys.stdin)['notebook_output']['result'])['space_id'])")
echo "    Genie space: $GENIE_SPACE_ID"
databricks bundle deploy -t "$TARGET" "$@" --var="genie_space_id=$GENIE_SPACE_ID"

echo "==> [4/4] Granting the app identity and starting the app"
python3 "$SCRIPT_DIR/grant_app_access.py" --target "$TARGET" --genie-space-id "$GENIE_SPACE_ID" "$@"
databricks bundle run fna_control_tower_app -t "$TARGET" "$@" --var="genie_space_id=$GENIE_SPACE_ID"

echo ""
echo "Setup complete. Inspect resources with: databricks bundle summary -t $TARGET"
