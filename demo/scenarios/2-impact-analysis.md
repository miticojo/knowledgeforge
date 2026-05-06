# Scenario 2 — Cosa si rompe se decommissioni X?

**Audience**: platform engineering lead, change-management board.
**Goal**: show the difference between asking an LLM "what depends on Redis?" (vector-only guess) and asking the *graph* (deterministic BFS).
**Dataset**: `microservices-demo` from Scenario 1 (assumes seed already ran).

## Setup

```bash
# Make sure backend is up and the microservices-demo graph is populated
bash demo/scripts/seed.sh --dataset microservices-demo --skip-if-loaded
```

## The question

> "If we decommission `redis-cart`, what breaks?"

### Pass 1 — Vector-only (the strawman)

Disable the graph in the agent (UI toggle: *Retrieval → Vector only*) and ask the question.

- **Expected behavior**: agent returns a plausible-sounding paragraph mentioning the cart service and "possibly the frontend", with low specificity and no hop count.
- **Talking point**: this is what a stock RAG stack looks like. It's *not wrong*, but you cannot make a change-management decision from it.
- **Screenshot**: `screenshots/2-step-1-vector-only.png`

### Pass 2 — Graph-backed impact analysis

Re-enable graph retrieval, then call the impact endpoint directly to make the determinism visible:

```bash
curl -s "http://localhost:8080/graph/impact/Component/redis-cart?max_hops=3" | jq
```

Expected JSON shape (illustrative):

```json
{
  "root": {"type": "Component", "name": "redis-cart"},
  "impacted": [
    {"name": "cartservice",   "type": "Component", "hop": 1, "edge": "uses",       "confidence": "EXTRACTED"},
    {"name": "frontend",      "type": "Component", "hop": 2, "edge": "calls",      "confidence": "EXTRACTED"},
    {"name": "checkoutservice","type": "Component","hop": 2, "edge": "calls",      "confidence": "INFERRED"},
    {"name": "Online Boutique UI", "type": "Service", "hop": 3, "edge": "realizes", "confidence": "INFERRED"}
  ],
  "max_hops": 3,
  "total_impacted": 4
}
```

Then ask the same chat question with graph enabled.

- **Expected behavior**: agent grounds its answer in the BFS result. It enumerates the impacted services with hop count, attaches confidence labels, and flags any INFERRED edges as "verify before action".
- **Talking point**: the graph makes the impact *enumerable* and *auditable*. No hallucinated fan-out, no missed transitive dependency.
- **Screenshot**: `screenshots/2-step-2-graph.png`

### Pass 3 — Side-by-side

Open the graph view, click the `redis-cart` node, hit "highlight impact radius (3 hops)". The same answer appears visually.

- **Talking point**: presenter and audience can verify the agent's claim by eye.
- **Screenshot**: `screenshots/2-step-3-graph-view.png`

## Why this matters

- Vector-only RAG cannot answer "what breaks?" reliably because it pattern-matches token similarity, not topology.
- Graph BFS is O(impacted-set), bounded, and reproducible — give the same graph, you get the same answer.
- The confidence labels (EXTRACTED / INFERRED / AMBIGUOUS) tell the presenter where the model used heuristics vs hard evidence — this is the bridge to human review.

## Cleanup

No state to reset; impact endpoint is read-only.
