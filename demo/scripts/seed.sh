#!/usr/bin/env bash
# KnowledgeForge demo seed script.
#
# Waits for spanner-emulator + kb-agent, initializes the emulator schema,
# then ingests all repos from demo/datasets/repos.txt via POST /ingest/git.
# Idempotent: if the graph already has > MIN_ENTITIES entities, the script
# exits early.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATASETS="$REPO_ROOT/demo/datasets"
AGENT_URL="${AGENT_URL:-http://localhost:8080}"
EMULATOR_HOST="${SPANNER_EMULATOR_HOST_HOSTPORT:-localhost:9010}"
MIN_ENTITIES="${MIN_ENTITIES:-100}"

log()  { printf "\033[1;36m[seed]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[seed]\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[1;31m[seed]\033[0m %s\n" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Wait for spanner emulator (TCP)
# ---------------------------------------------------------------------------
log "Waiting for spanner-emulator on $EMULATOR_HOST (30s) ..."
for i in $(seq 1 30); do
  if (echo > "/dev/tcp/${EMULATOR_HOST%:*}/${EMULATOR_HOST##*:}") 2>/dev/null; then
    log "  emulator up."
    break
  fi
  sleep 1
  [[ $i -eq 30 ]] && die "spanner-emulator not reachable after 30s"
done

# ---------------------------------------------------------------------------
# 2. Wait for kb-agent
# ---------------------------------------------------------------------------
log "Waiting for kb-agent at $AGENT_URL/health (60s) ..."
for i in $(seq 1 60); do
  if curl -sf "$AGENT_URL/health" >/dev/null 2>&1 \
     || curl -sf "$AGENT_URL/docs"   >/dev/null 2>&1; then
    log "  kb-agent up."
    break
  fi
  sleep 1
  [[ $i -eq 60 ]] && die "kb-agent not reachable after 60s"
done

# ---------------------------------------------------------------------------
# 3. Initialize emulator (project / instance / database / schema)
# ---------------------------------------------------------------------------
log "Initializing emulator schema ..."
SPANNER_EMULATOR_HOST="$EMULATOR_HOST" \
  SPANNER_PROJECT="${SPANNER_PROJECT:-demo-project}" \
  SPANNER_INSTANCE="${SPANNER_INSTANCE:-demo-instance}" \
  SPANNER_DATABASE="${SPANNER_DATABASE:-demo-db}" \
  python "$REPO_ROOT/kb-agent/scripts/init_emulator.py" \
  || die "init_emulator.py failed"

# ---------------------------------------------------------------------------
# 4. Idempotency check — skip if graph already populated
# ---------------------------------------------------------------------------
current_entities="$(curl -sf "$AGENT_URL/graph/stats" | jq -r '.entity_count // .entities // 0' 2>/dev/null || echo 0)"
if [[ "${current_entities:-0}" =~ ^[0-9]+$ ]] && (( current_entities >= MIN_ENTITIES )); then
  log "Graph already has $current_entities entities (>= $MIN_ENTITIES). Skipping ingestion."
  exit 0
fi

# ---------------------------------------------------------------------------
# 4b. Ingest the local ArchiSurance multi-layer dataset (ephemeral git repo)
# ---------------------------------------------------------------------------
ARCHISURANCE_DIR="$DATASETS/archisurance"
ARCHI_CONTAINER="${KB_AGENT_CONTAINER:-kf-kb-agent}"
if [[ -d "$ARCHISURANCE_DIR" ]]; then
  log "Building ephemeral git repo from $ARCHISURANCE_DIR ..."
  TMP_REPO="$(mktemp -d -t archisurance.XXXXXX)"
  cp -r "$ARCHISURANCE_DIR"/. "$TMP_REPO/"
  ( cd "$TMP_REPO" && git init -q && git add -A \
    && git -c user.email=demo@local -c user.name=demo commit -q -m initial ) \
    || warn "  failed to build ephemeral repo"
  # Copy into the kb-agent container so file:// is reachable from inside.
  IN_CONTAINER_PATH="/tmp/archisurance-demo"
  if docker exec "$ARCHI_CONTAINER" rm -rf "$IN_CONTAINER_PATH" 2>/dev/null \
     && docker cp "$TMP_REPO/." "$ARCHI_CONTAINER:$IN_CONTAINER_PATH" 2>/dev/null; then
    archi_url="file://$IN_CONTAINER_PATH"
    docker exec "$ARCHI_CONTAINER" git config --global --add safe.directory '*' 2>/dev/null || true
  else
    warn "  docker cp failed; falling back to host path (will likely not resolve in container)"
    archi_url="file://$TMP_REPO"
  fi
  archi_payload="$(jq -cn \
    --arg url "$archi_url" \
    '{repo_url:$url, include:["**/*.py","**/*.sql","**/*.md"], exclude:["dbt/target/**"]}')"
  log "  → POST /ingest/git $archi_url"
  archi_resp="$(curl -sf -X POST "$AGENT_URL/ingest/git" \
        -H 'Content-Type: application/json' \
        -d "$archi_payload")" || warn "  archisurance ingest failed"
  if [[ -n "${archi_resp:-}" ]]; then
    archi_job="$(echo "$archi_resp" | jq -r '.job_id')"
    log "    job_id=$archi_job"
    for i in $(seq 1 60); do
      sleep 5
      st="$(curl -sf "$AGENT_URL/ingest/git/$archi_job" | jq -r '.status' 2>/dev/null || echo unknown)"
      case "$st" in
        complete) log "    ✓ archisurance complete"; break ;;
        failed)   warn "    ✗ archisurance failed: $(curl -s $AGENT_URL/ingest/git/$archi_job | jq -r .error)"; break ;;
        *)        printf "." ;;
      esac
    done
    echo
  fi
fi

# ---------------------------------------------------------------------------
# 5. Ingest each repo from repos.txt (TSV: repo_url\tcommit_sha\tinclude\texclude)
# ---------------------------------------------------------------------------
REPOS_FILE="$DATASETS/repos.txt"
[[ -f "$REPOS_FILE" ]] || die "missing $REPOS_FILE"

log "Ingesting repos from $REPOS_FILE ..."
while IFS=$'\t' read -r repo_url commit_sha includes excludes; do
  [[ -z "${repo_url:-}" || "$repo_url" == "repo_url" || "${repo_url:0:1}" == "#" ]] && continue

  # Convert csv globs to JSON arrays
  inc_json="$(jq -Rcn --arg s "$includes" '$s | split(",")')"
  exc_json="$(jq -Rcn --arg s "$excludes" '$s | split(",")')"

  payload="$(jq -cn \
    --arg url "$repo_url" \
    --arg ref "$commit_sha" \
    --argjson inc "$inc_json" \
    --argjson exc "$exc_json" \
    '{repo_url:$url, ref:$ref, include:$inc, exclude:$exc}')"

  log "  → POST /ingest/git $repo_url@${commit_sha:0:7}"
  resp="$(curl -sf -X POST "$AGENT_URL/ingest/git" \
            -H 'Content-Type: application/json' \
            -d "$payload")" || { warn "  request failed; continuing"; continue; }
  job_id="$(echo "$resp" | jq -r '.job_id')"
  log "    job_id=$job_id"

  # Poll for terminal status (max 10 minutes per repo)
  for i in $(seq 1 120); do
    sleep 5
    status="$(curl -sf "$AGENT_URL/ingest/git/$job_id" | jq -r '.status' 2>/dev/null || echo unknown)"
    case "$status" in
      complete) log "    ✓ complete"; break ;;
      failed)   warn "    ✗ failed: $(curl -s $AGENT_URL/ingest/git/$job_id | jq -r .error)"; break ;;
      *)        printf "." ;;
    esac
    [[ $i -eq 120 ]] && warn "    timeout waiting for job"
  done
  echo
done < "$REPOS_FILE"

# ---------------------------------------------------------------------------
# 6. Optional: PDF ingestion (if fetch_pdfs.sh present and PDFs listed)
# ---------------------------------------------------------------------------
if [[ -x "$DATASETS/fetch_pdfs.sh" && -f "$DATASETS/pdfs.txt" ]]; then
  log "Fetching PDFs ..."
  ( cd "$DATASETS" && ./fetch_pdfs.sh ) || warn "fetch_pdfs.sh failed; skipping"
  # NOTE: PDF parsing is degraded in DEMO_MODE (liteparse is mocked).
  # We skip the upload loop here on purpose — git ingestion is the demo focus.
fi

# ---------------------------------------------------------------------------
# 7. Print final stats
# ---------------------------------------------------------------------------
log "Final graph stats:"
curl -sf "$AGENT_URL/graph/stats" | jq . || warn "stats endpoint unreachable"
log "Seeding complete."
