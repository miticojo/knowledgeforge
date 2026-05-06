#!/usr/bin/env bash
# KnowledgeForge demo recorder.
#
# Boots the demo stack, swaps in a tiny single-repo dataset for fast recording,
# captures an asciinema cast of seed.sh + queries.sh, restores state, and
# converts the cast to SVG via svg-term-cli.
#
# Usage:  bash demo/scripts/record.sh
# Output: demo/recording/walkthrough.cast
#         demo/recording/walkthrough.svg
#
# Idempotent. Safe to re-run. Never echoes or copies GEMINI_API_KEY.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

REC_DIR="$REPO_ROOT/demo/recording"
CAST="$REC_DIR/walkthrough.cast"
SVG="$REC_DIR/walkthrough.svg"
REPOS_FILE="$REPO_ROOT/demo/datasets/repos.txt"
REPOS_BACKUP="$REPOS_FILE.recordbak"
COMPOSE_FILE="$REPO_ROOT/docker-compose.demo.yml"
ENV_FILE="$REPO_ROOT/kb-agent/.env"

# Host port for kb-agent. Override if 8080 is busy on this machine.
HOST_AGENT_PORT="${HOST_AGENT_PORT:-8090}"
HOST_FRONTEND_PORT="${HOST_FRONTEND_PORT:-3010}"
HOST_SPANNER_PORT="${HOST_SPANNER_PORT:-9110}"
export AGENT_URL="http://localhost:${HOST_AGENT_PORT}"
export SPANNER_EMULATOR_HOST_HOSTPORT="localhost:${HOST_SPANNER_PORT}"

OVERRIDE_FILE="$REC_DIR/.compose.override.yml"

# A small Flask-org library: pallets/itsdangerous, recent SHA from ls-remote.
ITSDANG_SHA="${ITSDANG_SHA:-672971d66a2ef9f85151e53283113f33d642dabd}"

log()  { printf "\033[1;36m[record]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[record]\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[1;31m[record]\033[0m %s\n" "$*" >&2; exit 1; }

mkdir -p "$REC_DIR"

# ---------------------------------------------------------------------------
# 0. Tooling sanity
# ---------------------------------------------------------------------------
command -v asciinema >/dev/null || die "asciinema not installed (brew install asciinema)"
command -v svg-term  >/dev/null || die "svg-term not installed (npm i -g svg-term-cli)"
command -v docker    >/dev/null || die "docker not installed"
docker info >/dev/null 2>&1     || die "docker daemon not running"

# ---------------------------------------------------------------------------
# 1. Load env (kb-agent/.env). Never print contents.
# ---------------------------------------------------------------------------
[[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
[[ -n "${GEMINI_API_KEY:-}" ]] || die "GEMINI_API_KEY not set after sourcing $ENV_FILE"
log "GEMINI_API_KEY loaded into env (length=${#GEMINI_API_KEY})"

# Make sure GEMINI_API_KEY is exported to children (compose) but NEVER printed.
export GEMINI_API_KEY

# kb-agent/.env contains placeholder GOOGLE_CLOUD_PROJECT / SPANNER_* values
# (your-gcp-project / your-spanner-instance / your-spanner-database) intended
# for *production* use against real GCP. Inside the demo stack the kb-agent
# container is wired to demo-project/demo-instance/demo-db via docker-compose.
# We must override the *host-side* env we just sourced so seed.sh's
# init_emulator.py and queries.sh see the same names. Otherwise init creates
# the wrong instance and every /graph/* query 404s.
export GOOGLE_CLOUD_PROJECT="demo-project"
export SPANNER_PROJECT="demo-project"
export SPANNER_INSTANCE="demo-instance"
export SPANNER_DATABASE="demo-db"

PLACEHOLDER_SVG=$(cat <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="600" height="80">
  <rect width="100%" height="100%" fill="#1a1a1a"/>
  <text x="20" y="45" fill="#fafafa" font-family="monospace" font-size="18">Demo recording pending</text>
</svg>
EOF
)
write_placeholder() {
  printf "%s\n" "$PLACEHOLDER_SVG" > "$SVG"
  warn "Wrote placeholder SVG -> $SVG"
}

# Always restore repos.txt and tear down on exit.
cleanup() {
  local rc=$?
  if [[ -f "$REPOS_BACKUP" ]]; then
    mv -f "$REPOS_BACKUP" "$REPOS_FILE"
    log "Restored repos.txt from backup"
  fi
  log "docker compose down -v ..."
  if [[ -f "$OVERRIDE_FILE" ]]; then
    docker compose -f "$COMPOSE_FILE" -f "$OVERRIDE_FILE" down -v >/dev/null 2>&1 || true
  else
    docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1 || true
  fi
  rm -f "$OVERRIDE_FILE"
  if [[ ! -s "$SVG" ]]; then
    write_placeholder
  fi
  exit "$rc"
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# 2. Boot the stack (with port override so we don't collide with anything
#    already bound on 8080/3000/9010 on the host).
# ---------------------------------------------------------------------------
cat > "$OVERRIDE_FILE" <<EOF
services:
  kb-agent:
    ports: !override
      - "${HOST_AGENT_PORT}:8080"
  kb-frontend:
    ports: !override
      - "${HOST_FRONTEND_PORT}:3000"
    environment:
      NEXT_PUBLIC_BACKEND_URL: "http://localhost:${HOST_AGENT_PORT}"
  spanner-emulator:
    ports: !override
      - "${HOST_SPANNER_PORT}:9010"
      - "9120:9020"
EOF
log "Compose override -> $OVERRIDE_FILE (agent:${HOST_AGENT_PORT}, frontend:${HOST_FRONTEND_PORT}, spanner:${HOST_SPANNER_PORT})"

REBUILD="${REBUILD:-1}"
if [[ "$REBUILD" == "1" ]]; then
  log "REBUILD=1 -> docker compose build --no-cache kb-agent (ensures fresh Dockerfile w/ git) ..."
  docker compose -f "$COMPOSE_FILE" -f "$OVERRIDE_FILE" build --no-cache kb-agent
else
  log "REBUILD=0 -> skipping kb-agent rebuild (export REBUILD=1 to force)."
fi

log "Bringing up demo stack ..."
docker compose -f "$COMPOSE_FILE" -f "$OVERRIDE_FILE" up -d

log "Waiting for kb-agent ${AGENT_URL}/health (max 120s) ..."
ok=0
for i in $(seq 1 120); do
  if curl -sf "${AGENT_URL}/health" >/dev/null 2>&1; then
    ok=1; log "  kb-agent healthy."; break
  fi
  sleep 1
done
[[ $ok -eq 1 ]] || die "kb-agent did not become healthy within 120s"

# ---------------------------------------------------------------------------
# 3. Swap in tiny single-repo dataset (pallets/itsdangerous)
# ---------------------------------------------------------------------------
[[ -f "$REPOS_FILE" ]] || die "missing $REPOS_FILE"
cp "$REPOS_FILE" "$REPOS_BACKUP"
{
  printf "repo_url\tcommit_sha\tinclude_globs\texclude_globs\n"
  printf "https://github.com/pallets/itsdangerous\t%s\t**/*.py\ttests/**,docs/**\n" "$ITSDANG_SHA"
} > "$REPOS_FILE"
log "Swapped repos.txt -> pallets/itsdangerous@${ITSDANG_SHA:0:7}"

# ---------------------------------------------------------------------------
# 4. Record asciinema cast
# ---------------------------------------------------------------------------
log "Recording asciinema cast -> $CAST"
rm -f "$CAST"
asciinema rec "$CAST" \
  --overwrite \
  --idle-time-limit 5 \
  --command "bash $REPO_ROOT/demo/scripts/walkthrough_narrated.sh" \
  || warn "asciinema rec returned non-zero (continuing)"

if [[ ! -s "$CAST" ]]; then
  warn "Cast file empty or missing; producing placeholder SVG."
  write_placeholder
  exit 0
fi

# ---------------------------------------------------------------------------
# 5. Normalize cast format. asciinema 3.x writes v3, but svg-term-cli only
#    reads v1/v2. If the header is v3, downgrade in place.
# ---------------------------------------------------------------------------
if head -1 "$CAST" | grep -q '"version":3'; then
  log "Converting cast v3 -> v2 for svg-term compatibility ..."
  python3 - "$CAST" <<'PY'
import json, sys
src = sys.argv[1]
with open(src) as f:
    lines = f.readlines()
hdr = json.loads(lines[0])
v2 = {
    "version": 2,
    "width":  hdr.get("term", {}).get("cols", 80),
    "height": hdr.get("term", {}).get("rows", 24),
    "timestamp": hdr.get("timestamp", 0),
    "env": hdr.get("env", {}),
    "idle_time_limit": hdr.get("idle_time_limit", 2),
}
out = [json.dumps(v2)]
t = 0.0
for ln in lines[1:]:
    ln = ln.strip()
    if not ln:
        continue
    ev = json.loads(ln)
    t += float(ev[0])
    out.append(json.dumps([round(t, 6), ev[1], ev[2]]))
with open(src, "w") as f:
    f.write("\n".join(out) + "\n")
PY
fi

# ---------------------------------------------------------------------------
# 6. Convert to SVG (keep dimensions tight to stay under 500KB)
# ---------------------------------------------------------------------------
log "Converting to SVG ..."
svg-term --in "$CAST" --out "$SVG" --window --no-cursor --width 100 --height 30 \
  || { warn "svg-term failed"; write_placeholder; }

# ---------------------------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------------------------
cast_size=$(wc -c < "$CAST" | tr -d ' ')
svg_size=$(wc -c < "$SVG"  | tr -d ' ')
duration=$(jq -s 'map(select(type=="array")) | last | .[0]' "$CAST" 2>/dev/null \
           || awk 'NR>1 && $0 ~ /^\[/ {gsub(/[\[,]/,""); t=$1} END{print t+0}' "$CAST")
log "cast: ${cast_size} bytes"
log "svg:  ${svg_size} bytes"
log "duration: ${duration}s"
log "Done."
