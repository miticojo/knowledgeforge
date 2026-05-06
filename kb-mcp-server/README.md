# kb-mcp-server / kf-mcp

MCP stdio server that exposes the KnowledgeForge ArchiMate knowledge graph (8 tools) to AI assistants.

This directory ships **two distribution surfaces** for the same server:

1. **Python package** (`kb-mcp-server`, console-script `kb-mcp`) — the canonical implementation.
2. **Node shim** (`kf-mcp`, in `bin/kf-mcp.js`) — a thin wrapper so manifests can use the conventional `npx`-style command form.

## Installation

### Required: Python entrypoint

```bash
pip install -e .
# provides the `kb-mcp` console-script
```

Requires Python 3.10+.

### Optional: Node shim (`kf-mcp`)

The Node shim simply spawns `kb-mcp` (or `python3 -m kb_mcp_server` as fallback). It does **not** ship the Python code itself.

```bash
# locally (without npm publish):
node bin/kf-mcp.js --help
node bin/kf-mcp.js serve --backend-url https://kb-agent-XXXX.run.app
```

> **TODO — npm publication.** `kf-mcp` is **not yet published** to the npm registry. Manifests therefore use `kb-mcp serve …` directly, which requires the Python package to be installed. Once `kf-mcp` is published, the manifests can switch to `npx -y kf-mcp` for one-line install — but **even then, the Python package remains a hard prerequisite** because the shim shells out to it. The recommended workaround today: `pip install -e kb-mcp-server/` first, then either `kb-mcp …` or `npx kf-mcp …` works (the shim finds the Python entrypoint on PATH).

## Usage

```bash
kb-mcp serve --backend-url https://kb-agent-XXXX.run.app [--tenant user@example.com]
```

Environment:
- `BACKEND_URL` — required; URL of the `kb-agent` REST backend.
- `KF_TENANT` — optional; tenant id for multi-tenant scoping.

## Tools exposed

`get_brief`, `query`, `get_entity`, `get_connections`, `god_nodes`, `graph_stats`, `check_conformance`, `impact_analysis`.

See `../skills/knowledgeforge-architecture/SKILL.md` for trigger-prompt examples.

## CLI integrations

KnowledgeForge ships manifests for Gemini CLI, Claude Code, and Codex CLI at the repo root. See `../docs/integrations/README.md`.
