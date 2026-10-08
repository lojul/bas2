#!/usr/bin/env bash
# One-command deploy for the doc-pipeline App Service (and optionally the Function App).
#
# Usage:
#   ./deploy.sh              # deploy App Service (doc-pipeline)
#   ./deploy.sh --func       # also publish the Function App
#   ./deploy.sh --func-only  # publish Function App ONLY (fast — skips App Service)
#   ./deploy.sh --all        # everything (App Service + Function App)
#
# NOTE (2026-07-28): the prop-chat App Service (c21net-bas-api-prop-chat-ea-prod) was
# permanently deleted — it served the deprecated Next.js dashboard, which was also
# deleted. The old --chat flag is removed; running it against the deleted resource
# just hangs/fails against a dead hostname with no clear error. If a chat/search
# service is ever rebuilt, it belongs in its own deploy path, not bolted back onto
# this flag.
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
FUNC_APP="c21net-bas-func-doc-pipeline-ea-prod"

DO_FUNC=false; DO_FUNC_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --func)      DO_FUNC=true ;;
    --func-only) DO_FUNC_ONLY=true ;;
    --all)       DO_FUNC=true ;;
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

get_token() {
  az account get-access-token --resource "https://management.azure.com/" --query accessToken -o tsv
}

deploy_app() {
  local app="$1"
  echo "==> Deploying $app"
  local token
  token=$(get_token)

  # Remember the current top deployment so we can tell when the NEW one lands
  local prev_id
  prev_id=$(curl -s "https://${app}.scm.azurewebsites.net/api/deployments" \
    -H "Authorization: Bearer $token" \
    | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d[0]['id'] if d else '')
except Exception:
    print('')
" 2>/dev/null || echo "")

  # Retry zipdeploy up to 3 times (handles transient 409 conflicts)
  local code attempt
  for attempt in 1 2 3; do
    code=$(curl --http1.1 -s -o /dev/null -w "%{http_code}" -X POST \
      "https://${app}.scm.azurewebsites.net/api/zipdeploy?isAsync=true" \
      -H "Authorization: Bearer $token" \
      -H "Content-Type: application/octet-stream" \
      --data-binary @"$ZIP")
    [ "$code" = "202" ] && break
    echo "    zipdeploy returned HTTP $code (attempt $attempt/3), retrying in 20s..."
    sleep 20
    token=$(get_token)
  done
  if [ "$code" != "202" ]; then
    echo "ERROR: zipdeploy failed after 3 attempts (last HTTP $code)"
    exit 1
  fi

  echo "    waiting for Oryx build..."
  # Refresh token inside the loop — Oryx build takes ~5 min, token may age
  local poll=0
  while true; do
    poll=$((poll + 1))
    [ $((poll % 8)) -eq 0 ] && token=$(get_token)  # refresh every ~2 min
    done=$(curl -s "https://${app}.scm.azurewebsites.net/api/deployments" \
      -H "Authorization: Bearer $token" \
      | PREV_ID="$prev_id" python3 -c "
import json, os, sys
try:
    deps = json.load(sys.stdin)
    d = deps[0] if deps else {}
    new = d.get('id', '') != os.environ.get('PREV_ID', '')
    print('1' if (new and d.get('complete')) else '0')
except Exception:
    print('0')
" 2>/dev/null || echo "0")
    [ "$done" = "1" ] && break
    if [ "$poll" -gt 60 ]; then echo "ERROR: Oryx build timed out"; exit 1; fi
    sleep 15
  done

  echo "    uploading source to wwwroot via VFS..."
  token=$(get_token)  # fresh token for VFS uploads
  local vfs_ok=true
  while IFS= read -r -d '' pyfile; do
    rel="${pyfile#$DEPLOY_DIR/}"
    code=$(curl --http1.1 -s -o /dev/null -w "%{http_code}" -X PUT \
      "https://${app}.scm.azurewebsites.net/api/vfs/site/wwwroot/${rel}" \
      -H "Authorization: Bearer $token" \
      -H "Content-Type: application/octet-stream" \
      -H "If-Match: *" \
      --data-binary @"$pyfile")
    if [ "$code" != "201" ] && [ "$code" != "204" ]; then
      echo "    WARNING: VFS upload failed for $rel (HTTP $code)"
      vfs_ok=false
    fi
  done < <(find "$DEPLOY_DIR/src" "$DEPLOY_DIR/api" -name "*.py" -print0)
  $vfs_ok && echo "    VFS upload OK" || echo "    WARNING: some files failed to upload"

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

if ! $DO_FUNC_ONLY; then
  deploy_app "$APP"
fi

if $DO_FUNC || $DO_FUNC_ONLY; then
  echo "==> Publishing Function App"
  az account set --subscription "c21net-business-automation-stack"
  (cd "$LANGGRAPH_DIR" && func azure functionapp publish "$FUNC_APP" --python 2>&1 | tail -2)
fi

echo "==> Done"
