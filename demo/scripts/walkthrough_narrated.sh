#!/usr/bin/env bash
# KnowledgeForge — narrated, paced walkthrough for asciinema recording.
#
# Replaces the raw seed.sh + queries.sh dump with a 4-5 beat tour that
# pauses between commands so a viewer can actually read what is on screen.
#
# Beats:
#   1. Boot stack + apply schema  (delegates to seed.sh prerequisites)
#   2. Ingest pallets/itsdangerous (single Python repo) and watch progress
#   3. /graph/stats                — entity / edge totals
#   4. /graph/god-nodes            — top architectural hubs
#   5. /graph/brief                — LLM-generated executive summary
#   6. /copilotkit                 — one chat query, show streaming chunks
#
# Reads no secrets directly. Inherits AGENT_URL / SPANNER_* from caller
# (record.sh exports them). Never prints GEMINI_API_KEY.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AGENT_URL="${AGENT_URL:-http://localhost:8080}"
EMULATOR_HOST="${SPANNER_EMULATOR_HOST_HOSTPORT:-localhost:9010}"

# Pacing knobs — tweak if the recording feels too slow / fast.
PAUSE_SHORT="${PAUSE_SHORT:-2}"
PAUSE_MED="${PAUSE_MED:-3}"
PAUSE_LONG="${PAUSE_LONG:-4}"

C_BANNER='\033[1;36m'
C_NARR='\033[1;33m'
C_CMD='\033[2m'
C_NOTE='\033[2;37m'
C_OFF='\033[0m'

banner() {
  printf "\n"
  printf "${C_BANNER}════════════════════════════════════════════════════════════${C_OFF}\n"
  printf "${C_BANNER}  %s${C_OFF}\n" "$*"
  printf "${C_BANNER}════════════════════════════════════════════════════════════${C_OFF}\n"
  sleep "$PAUSE_SHORT"
}

narrate() {
  printf "\n${C_NARR}→ %s${C_OFF}\n" "$*"
  sleep 1
}

note() {
  printf "${C_NOTE}  %s${C_OFF}\n" "$*"
  sleep "$PAUSE_SHORT"
}

show_cmd() {
  printf "${C_CMD}\$ %s${C_OFF}\n" "$*"
}

run_cmd() {
  show_cmd "$@"
  eval "$@" || printf "(command failed)\n"
  sleep "$PAUSE_MED"
}

# ---------------------------------------------------------------------------
# STEP 1 — Stack already booted by record.sh; just confirm health.
# ---------------------------------------------------------------------------
banner "STEP 1 — Demo stack: kb-agent + Spanner emulator + frontend"

narrate "Confirm kb-agent is healthy"
run_cmd "curl -sf $AGENT_URL/health | jq ."
note "Agent is up. Spanner emulator is wired underneath at ${EMULATOR_HOST}."

# ---------------------------------------------------------------------------
# STEP 2 — Apply schema (idempotent) and ingest one Python repo.
# ---------------------------------------------------------------------------
banner "STEP 2 — Initialise Spanner schema + ingest pallets/itsdangerous"

narrate "Apply Spanner DDL (schema + migrations) to the emulator"
SPANNER_EMULATOR_HOST="$EMULATOR_HOST" \
  SPANNER_PROJECT="${SPANNER_PROJECT:-demo-project}" \
  SPANNER_INSTANCE="${SPANNER_INSTANCE:-demo-instance}" \
  SPANNER_DATABASE="${SPANNER_DATABASE:-demo-db}" \
  python "$REPO_ROOT/kb-agent/scripts/init_emulator.py" 2>&1 | tail -20
sleep "$PAUSE_MED"
note "Schema applied. Now ingest a real Python library from GitHub."

# Read the (single-repo) repos.txt prepared by record.sh.
REPOS_FILE="$REPO_ROOT/demo/datasets/repos.txt"
read -r _ < "$REPOS_FILE"  # skip header
IFS=$'\t' read -r repo_url commit_sha includes excludes < <(tail -n +2 "$REPOS_FILE")
inc_json="$(jq -Rcn --arg s "$includes" '$s | split(",")')"
exc_json="$(jq -Rcn --arg s "$excludes" '$s | split(",")')"
payload="$(jq -cn --arg url "$repo_url" --arg ref "$commit_sha" \
                  --argjson inc "$inc_json" --argjson exc "$exc_json" \
                  '{repo_url:$url, ref:$ref, include:$inc, exclude:$exc}')"

narrate "Kick off git ingestion: clone, parse, extract, write graph"
show_cmd "curl -X POST $AGENT_URL/ingest/git -d '{repo_url:\"$repo_url\", ...}'"
resp="$(curl -sf -X POST "$AGENT_URL/ingest/git" \
          -H 'Content-Type: application/json' -d "$payload")"
job_id="$(echo "$resp" | jq -r '.job_id')"
echo "  job_id=$job_id"
sleep "$PAUSE_SHORT"

narrate "Poll the job until it reports 'complete'"
show_cmd "curl $AGENT_URL/ingest/git/$job_id  # every 5s"
last_status=""
for i in $(seq 1 120); do
  status="$(curl -sf "$AGENT_URL/ingest/git/$job_id" | jq -r '.status' 2>/dev/null || echo unknown)"
  if [[ "$status" != "$last_status" ]]; then
    printf "  [t+%3ds] status=%s\n" "$((i*5))" "$status"
    last_status="$status"
  else
    printf "."
  fi
  case "$status" in
    complete) echo; echo "  ✓ ingestion complete"; break ;;
    failed)   echo; echo "  ✗ ingestion failed: $(curl -s $AGENT_URL/ingest/git/$job_id | jq -r .error)"; break ;;
  esac
  sleep 5
done
sleep "$PAUSE_MED"
note "Single Python repo → AST nodes → entities → graph edges, all in Spanner."

# ---------------------------------------------------------------------------
# STEP 3 — Show the populated graph at a glance.
# ---------------------------------------------------------------------------
banner "STEP 3 — /graph/stats: how big is the graph we just built?"

narrate "Total entities + edges across all entity types"
run_cmd "curl -sf $AGENT_URL/graph/stats | jq ."
note "Every number above came from a single ~5k LOC Python repo."

# ---------------------------------------------------------------------------
# STEP 4 — God-nodes: top architectural hubs.
# ---------------------------------------------------------------------------
banner "STEP 4 — /graph/god-nodes: most-connected entities (architectural hubs)"

narrate "Rank entities by edge count — these are the load-bearing parts"
run_cmd "curl -sf '$AGENT_URL/graph/god-nodes?top_n=10' | jq '.[:5]'"
note "These are the symbols every refactor will touch first."

# ---------------------------------------------------------------------------
# STEP 5 — Knowledge brief.
# ---------------------------------------------------------------------------
banner "STEP 5 — /graph/brief: LLM-generated executive summary"

narrate "Ask the agent for a one-paragraph description of the codebase"
run_cmd "curl -sf $AGENT_URL/graph/brief | jq ."
note "Brief is generated from graph topology + sampled entities."

# ---------------------------------------------------------------------------
# STEP 6 — One CopilotKit chat query.
# ---------------------------------------------------------------------------
banner "STEP 6 — /copilotkit: chat over the graph (streaming SSE)"

narrate "Ask a natural-language question; the agent retrieves + streams an answer"
prompt='What are the main signing and serialization classes in this library?'
echo "  prompt: $prompt"
sleep "$PAUSE_SHORT"

thread_id="t-$(uuidgen 2>/dev/null || echo $RANDOM-$RANDOM)"
run_id="r-$(uuidgen 2>/dev/null || echo $RANDOM-$RANDOM)"
msg_id="m-$(uuidgen 2>/dev/null || echo $RANDOM-$RANDOM)"
body="$(jq -cn --arg tid "$thread_id" --arg rid "$run_id" \
              --arg mid "$msg_id" --arg p "$prompt" \
              '{threadId:$tid, runId:$rid, state:{}, messages:[{id:$mid, role:"user", content:$p}], tools:[], context:[], forwardedProps:{}}')"
show_cmd "curl -N $AGENT_URL/copilotkit  # SSE stream, first 30 events"
curl -sN -X POST "$AGENT_URL/copilotkit" \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-Id: demo@local' \
  -H 'X-Search-Scope: all' \
  -d "$body" | head -n 30
sleep "$PAUSE_LONG"

note "End of walkthrough — the agent grounded its answer in graph entities."
banner "Done."
sleep "$PAUSE_SHORT"
