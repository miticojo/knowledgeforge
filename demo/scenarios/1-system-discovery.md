# Scenario 1 — Capisci un sistema sconosciuto in 5 minuti

**Audience**: solution architect / new-joiner facing an unfamiliar microservices estate.
**Goal**: from cold start (no docs, no tribal knowledge) to a usable mental model in five minutes.
**Dataset**: `microservices-demo` (Google Cloud Online Boutique) + ArchiSurance PDFs.

## Setup (one-time)

```bash
# Clones repos pinned in demo/datasets/repos.txt, fetches HTML pages, ingests
# everything into KnowledgeForge, builds the ArchiMate graph.
bash demo/scripts/seed.sh --dataset microservices-demo
# expected runtime: 4-6 minutes on a warm dev box
```

When the script returns you should see a populated graph at http://localhost:3000/architecture and a non-empty `/graph/stats` response from the backend.

## Live walkthrough — 5 queries, 1 minute each

### Query 1 — "Which services make up this system?"
- **Expected agent behavior**: keyword + vector retrieval; agent renders a list of `ApplicationComponent` nodes from the graph (frontend, cartservice, productcatalogservice, recommendationservice, paymentservice, shippingservice, emailservice, checkoutservice, currencyservice, adservice, loadgenerator).
- **Talking point**: the graph was extracted automatically — no team built this list by hand.
- **Screenshot**: `screenshots/1-step-1.png`

### Query 2 — "Show me the checkout flow end-to-end."
- **Expected behavior**: graph traversal via `serves` / `triggers` edges; agent stitches frontend → checkoutservice → (paymentservice, shippingservice, emailservice, currencyservice, productcatalogservice, cartservice).
- **Talking point**: vector-only retrieval would surface text snippets; graph traversal returns the *path*. Confidence labels on each edge tell us which hops are EXTRACTED vs INFERRED.
- **Screenshot**: `screenshots/1-step-2.png`

### Query 3 — "Which datastore does cartservice use?"
- **Expected behavior**: graph hop from `cartservice` (Component) → `redis-cart` (Node/TechService); agent cites the source code chunk that establishes the dependency.
- **Talking point**: every claim has a clickable source — answer is auditable.
- **Screenshot**: `screenshots/1-step-3.png`

### Query 4 — "What authentication pattern is used between services?"
- **Expected behavior**: hybrid retrieval; agent reports gRPC mutual auth via service mesh OR notes "not explicitly documented" and labels the conclusion UNSUPPORTED.
- **Talking point**: KnowledgeForge's verification pass tags every answer SUPPORTED / CONTRADICTED / UNSUPPORTED — the agent will not hallucinate.
- **Screenshot**: `screenshots/1-step-4.png`

### Query 5 — "List external dependencies and their failure modes."
- **Expected behavior**: agent fans out to `External` nodes (e.g., container registry, payment gateway placeholders), then queries the runbook documents for known failure modes.
- **Talking point**: cross-document synthesis — graph + PDF runbooks merged in one answer.
- **Screenshot**: `screenshots/1-step-5.png`

## Talking points for the presenter

- Open the graph viewer side-by-side with the chat. Every cited entity highlights in the graph as the agent answers.
- Mention that the graph follows ArchiMate 3.2 layers (Business / Application / Technology / Strategy / Implementation). The layer filter pills demonstrate this.
- If a question fails (returns UNSUPPORTED), reframe it as a feature: "the system told us what it doesn't know."

## Cleanup

```bash
bash demo/scripts/seed.sh --reset
```
