#!/usr/bin/env bash
# One-command deploy for the doc-pipeline App Service (and optionally the Function App).
#
# Usage:
#   ./deploy.sh              # deploy App Service (doc-pipeline)
#   ./deploy.sh --chat       # also deploy the prop-chat App Service
#   ./deploy.sh --func       # also publish the Function App
#   ./deploy.sh --all        # everything
#
# Guards against the known pitfalls:
#   - stale zip reuse (always deletes first, verifies timestamp)
#   - zipping the wrong directory (always zips the staged deploy dir)
#   - Oryx not updating wwwroot (explicit copy step)
#   - deploying without restart (explicit restart + health check)

set -euo pipefail

LANGGRAPH_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="/private/tmp/api_deploy_dir"
ZIP="/private/tmp/api-deploy.zip"
RG="c21net-bas-document-processor-ea-prod"
APP="c21net-bas-api-doc-pipeline-ea-prod"
CHAT_APP="c21net-bas-api-prop-chat-ea-prod"
FUNC_APP="c21net-bas-func-doc-pipeline-ea-prod"

DO_CHAT=false; DO_FUNC=false
for arg in "$@"; do
  case "$arg" in
    --chat) DO_CHAT=true ;;
    --func) DO_FUNC=true ;;
    --all)  DO_CHAT=true; DO_FUNC=true ;;
  esac
done

echo "==> Staging files"
rsync -a --delete "$LANGGRAPH_DIR/src/" "$DEPLOY_DIR/src/"
rsync -a --delete "$LANGGRAPH_DIR/api/" "$DEPLOY_DIR/api/"
cp "$LANGGRAPH_DIR/requirements-api.txt" "$DEPLOY_DIR/requirements.txt"
find "$DEPLOY_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "==> Building zip"
rm -f "$ZIP"
(cd "$DEPLOY_DIR" && zip -rq "$ZIP" . -x "*.DS_Store")
SIZE=$(du -k "$ZIP" | cut -f1)
if [ "$SIZE" -gt 5000 ]; then
  echo "ERROR: zip is ${SIZE}KB — looks like the wrong directory was zipped (venv?). Aborting."
  exit 1
fi
AGE=$(( $(date +%s) - $(stat -f %m "$ZIP") ))
if [ "$AGE" -gt 60 ]; then
  echo "ERROR: zip is ${AGE}s old — was not rebuilt. Aborting."
  exit 1
fi
echo "    zip OK (${SIZE}KB, ${AGE}s old)"

deploy_app() {
  local app="$1"
  echo "==> Deploying $app"
  local token
  token=$(az account get-access-token --resource "https://management.azure.com/" --query accessToken -o tsv)

  # Remember the current top deployment so we can tell when the NEW one lands
  local prev_id
  prev_id=$(curl -s "https://${app}.scm.azurewebsites.net/api/deployments" \
    -H "Authorization: Bearer $token" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null || echo "")

  local code
  code=$(curl --http1.1 -s -o /dev/null -w "%{http_code}" -X POST \
    "https://${app}.scm.azurewebsites.net/api/zipdeploy?isAsync=true" \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/octet-stream" \
    --data-binary @"$ZIP")
  if [ "$code" != "202" ]; then
    echo "ERROR: zipdeploy returned HTTP $code"
    exit 1
  fi

  echo "    waiting for Oryx build..."
  until curl -s "https://${app}.scm.azurewebsites.net/api/deployments" \
      -H "Authorization: Bearer $token" \
      | PREV_ID="$prev_id" python3 -c "
import json, os, sys
deps = json.load(sys.stdin)
d = deps[0] if deps else {}
new = d.get('id', '') != os.environ.get('PREV_ID', '')
sys.exit(0 if (new and d.get('complete')) else 1)
"; do
    sleep 15
  done

  echo "    copying source to wwwroot..."
  local out
  out=$(curl -s -X POST "https://${app}.scm.azurewebsites.net/api/command" \
    -H "Authorization: Bearer $token" -H "Content-Type: application/json" \
    -d '{"command": "sh -c \"cp -rf /tmp/zipdeploy/extracted/src /home/site/wwwroot/src && cp -rf /tmp/zipdeploy/extracted/api /home/site/wwwroot/api && echo ok\"", "dir": "/"}')
  echo "$out" | grep -q '"ExitCode":0' || { echo "ERROR: wwwroot copy failed: $out"; exit 1; }

  echo "    restarting..."
  az webapp restart --name "$app" --resource-group "$RG" > /dev/null

  echo "    health check..."
  local tries=0
  until curl -s --max-time 10 "https://${app}.azurewebsites.net/api/health" | grep -q "ok"; do
    tries=$((tries + 1))
    if [ "$tries" -gt 40 ]; then echo "ERROR: health check timed out"; exit 1; fi
    sleep 5
  done
  echo "    $app healthy ✓"
}

deploy_app "$APP"
$DO_CHAT && deploy_app "$CHAT_APP"

if $DO_FUNC; then
  echo "==> Publishing Function App"
  az account set --subscription "c21net-business-automation-stack"
  (cd "$LANGGRAPH_DIR" && func azure functionapp publish "$FUNC_APP" --python 2>&1 | tail -2)
fi

echo "==> Done"
