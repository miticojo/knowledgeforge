# Graph Navigation

The `/graph` page is a standalone navigable canvas over the KnowledgeForge
ArchiMate graph. It complements the inline graph rendered next to a search
result by giving the user a full-screen exploration surface that's not tied
to a particular question.

## What's on the page

- **Canvas** — `react-force-graph-2d` rendering with ArchiMate layer
  clustering and proportional node sizing (degree-weighted).
- **Filter sidebar** — five layer toggles (Strategy, Business, Application,
  Technology, Motivation), entity-type checkboxes, hub/orphan filters
  (degree thresholds), and a search box that highlights matching nodes.
- **Selection panel** — clicking a node pins it as the focus: the panel
  shows its ArchiMate type, source documents, confidence-labeled
  outgoing/incoming edges, and a one-click "explore neighborhood" action
  that re-roots the canvas on its 1-hop and 2-hop neighbours.

## Backend endpoints

The page is powered by two read-only graph-navigation endpoints (added in
Milestone J alongside the page itself):

| Endpoint | Purpose |
|---|---|
| `GET /graph/search?q=<term>&limit=N` | Substring + embedding search across all 22 entity tables. Returns `{entity_id, type, name, score}` for the top matches. |
| `GET /graph/neighbors?entity_id=<id>&hops=1\|2` | Returns the subgraph rooted at `entity_id`. Each edge carries its `confidence` label (`EXTRACTED` / `INFERRED` / `AMBIGUOUS`). |

Both endpoints honour the `tenant_id` filter from `TenantMiddleware`
(see [`multi-tenancy.md`](../multi-tenancy.md)) — graph navigation is always
scoped to what the calling user can see.

## Entity scope filter for chat

The same selection mechanism feeds the **chat scope filter**: when a user
pins an entity in `/graph` (or types `@entity` in `/chat`), the chat panel
sets the `X-Entity-Scope: <entity_id>` header on every CopilotKit request.
The `SearchAgent` reads this header in `tool_query_spanner_graph` and
restricts seed-chunk retrieval to chunks that mention the scoped entity
(`ChunkMentions` join), then expands via the usual graph-traversal step
constrained to the scoped entity's neighbourhood.

The scope is **request-pinned** at the start of the search (see commit
`76c141d` — "fix: pin tenant scope at search start to prevent race
condition") so that streaming results don't get reshuffled if the user
changes the focus mid-stream. To clear the scope, dismiss the banner in
the chat header — the next request will fall back to full graph search.

## Why a separate page

The inline graph next to a search answer is optimised for showing *why a
particular answer cited what it cited*. The `/graph` page is optimised for
the opposite direction: starting from a question about the system itself
(e.g. *"what does this codebase look like?"*) and progressively narrowing
down to the entities that matter. The two views share the same
`react-force-graph-2d` component and the same backend endpoints, but the
sidebar and selection-panel UX is what makes `/graph` usable as a
standalone exploration tool rather than a result-explanation device.
