# KnowledgeForge — CLI integrations

KnowledgeForge ships as an MCP plug-in for three AI coding assistants:

| CLI | Manifest | Install command |
|---|---|---|
| Gemini CLI | `gemini-extension.json` | `bash kf-install.sh gemini` |
| Claude Code | `.claude-plugin/plugin.json` | `bash kf-install.sh claude` |
| Codex CLI | `.codex-plugin/plugin.json` | `bash kf-install.sh codex` |

All three register the same MCP stdio server (`knowledgeforge`) exposing 8 tools: `get_brief`, `query`, `get_entity`, `get_connections`, `god_nodes`, `graph_stats`, `check_conformance`, `impact_analysis`. The accompanying skill (`skills/knowledgeforge-architecture/SKILL.md`) tells the assistant when to invoke each one.

## Prerequisites (all CLIs)

1. **Python 3.10+** and the KF MCP server installed:
   ```bash
   pip install -e kb-mcp-server/
   ```
   This provides the `kb-mcp` console-script that the manifests invoke.
2. A reachable `kb-agent` backend (Cloud Run URL or local `python kb-agent/main.py`).
3. Environment variables set in the shell that launches the CLI:
   - `BACKEND_URL` — required; e.g. `https://kb-agent-XXXX.run.app`.
   - `KF_TENANT` — optional; tenant email for multi-tenant scoping.

## npm publication status

> **TODO.** `kf-mcp` (the Node shim in `kb-mcp-server/bin/kf-mcp.js`) is **not yet published** to npm. Until it is, manifests use `kb-mcp serve …` directly, which requires the Python install above. **Workaround that already works today**: after `pip install -e kb-mcp-server/`, you can also run `npx kf-mcp serve --backend-url …` locally — the Node shim simply shells out to the installed Python entrypoint. Once published, manifests will switch to `npx -y kf-mcp` for true zero-config install (Python install will still be required as a runtime dep).

## Per-CLI guides

- [Gemini CLI](./gemini-cli.md)
- [Claude Code](./claude-code.md)
- [Codex CLI](./codex.md)
