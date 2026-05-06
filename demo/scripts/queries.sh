#!/usr/bin/env bash
# KnowledgeForge demo queries — 10 illustrative API calls covering the
# 3 scenarios in demo/scenarios/. Pretty-printed via jq for the presenter.

set -uo pipefail

AGENT_URL="${AGENT_URL:-http://localhost:8080}"

hr()    { printf "\n\033[1;35m────────────────────────────────────────────────────────\033[0m\n"; }
title() { hr; printf "\033[1;36m▶ %s\033[0m\n" "$*"; printf "\033[2m%s\033[0m\n" "$1"; }
run()   { printf "\033[2m\$ %s\033[0m\n" "$*"; eval "$@" || printf "\033[31m(query failed)\033[0m\n"; }

# Helper: copilotkit POST returns SSE; we just dump first 40 lines.
# Schema: ag_ui.core.RunAgentInput — required fields are
#   threadId, runId, state, messages[], tools[], context[], forwardedProps
# UserMessage requires id, role="user", and string content.
# Schema source: /opt/homebrew/lib/python3.14/site-packages/ag_ui/core
ck() {
  local prompt="$1"
  local thread_id="t-$(uuidgen 2>/dev/null || echo $RANDOM-$RANDOM)"
  local run_id="r-$(uuidgen 2>/dev/null || echo $RANDOM-$RANDOM)"
  local msg_id="m-$(uuidgen 2>/dev/null || echo $RANDOM-$RANDOM)"
  local body
  body="$(jq -cn \
    --arg tid "$thread_id" --arg rid "$run_id" --arg mid "$msg_id" --arg p "$prompt" \
    '{
       threadId: $tid,
       runId: $rid,
       state: {},
       messages: [{id: $mid, role: "user", content: $p}],
       tools: [],
       context: [],
       forwardedProps: {}
     }')"
  curl -sN -X POST "$AGENT_URL/copilotkit" \
    -H 'Content-Type: application/json' \
    -H 'X-Tenant-Id: demo@local' \
    -H 'X-Search-Scope: all' \
    -d "$body" | head -n 40
}

# ===========================================================================
# Scenario 1 — System Discovery
# ===========================================================================
title "1/10  Graph stats — overall size of the knowledge graph"
run "curl -sf $AGENT_URL/graph/stats | jq ."

title "2/10  Knowledge brief — auto-generated executive summary"
run "curl -sf $AGENT_URL/graph/brief | jq ."

title "3/10  God-nodes — top-10 most connected entities"
run "curl -sf '$AGENT_URL/graph/god-nodes?top_n=10' | jq ."

title "4/10  CopilotKit chat — 'What components are in this microservices system?'"
run "ck 'What components are in this microservices system?'"

# ===========================================================================
# Scenario 2 — Impact Analysis
# ===========================================================================
title "5/10  Pick a sample ApplicationComponent from god-nodes for impact analysis"
SAMPLE_COMP="$(curl -sf "$AGENT_URL/graph/god-nodes?top_n=20" \
              | jq -r '.[] | select(.entity_type=="ApplicationComponent") | .entity_name' \
              | head -n1)"
SAMPLE_COMP="${SAMPLE_COMP:-cartservice}"
echo "Sample component: $SAMPLE_COMP"

title "6/10  Impact analysis (3 hops) for $SAMPLE_COMP"
run "curl -sf '$AGENT_URL/graph/impact/ApplicationComponent/$SAMPLE_COMP?max_hops=3' | jq ."

title "7/10  Direct connections for $SAMPLE_COMP"
run "curl -sf '$AGENT_URL/graph/connections/$SAMPLE_COMP' | jq ."

title "8/10  CopilotKit chat — 'What breaks if we change $SAMPLE_COMP?'"
run "ck 'What breaks if we change ${SAMPLE_COMP}?'"

# ===========================================================================
# Scenario 3 — Doc to Catalog / Conformance
# ===========================================================================
title "9/10  Conformance report — graph vs ontology coverage"
run "curl -sf $AGENT_URL/graph/conformance | jq ."

title "10/10 Tenant stats — per-tenant entity counts and last activity"
run "curl -sf $AGENT_URL/tenant/stats | jq ."

hr
echo "Done."
