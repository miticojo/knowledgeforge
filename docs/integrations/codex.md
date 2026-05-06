# KnowledgeForge for Codex CLI

## Install

```bash
# 1. Install the Python MCP server entrypoint
pip install -e kb-mcp-server/

# 2. Install the Codex plugin manifest
bash kf-install.sh codex
# -> ~/.codex/plugins/knowledgeforge/plugin.json

# 3. Configure backend
export BACKEND_URL=https://kb-agent-XXXX.run.app
export KF_TENANT=you@example.com   # optional
```

## Verify

Restart Codex CLI and check the MCP server registry. The exact command depends on your Codex CLI version; consult `codex --help` or the Codex plugin docs. The `knowledgeforge` server should appear with its 8 tools.

> **Note:** Codex CLI was **not installed in the environment where these manifests were authored**, so end-to-end install verification is left to you. The manifest follows the same schema as the Gemini and Claude variants and has been JSON-linted.

## Example prompt

> **User:** "Find all DataObjects accessed by the OrderProcessing business process and show their connections."

**Expected agent behavior:**
1. Calls `knowledgeforge.query` with the natural-language question.
2. For each returned `DataObject`, calls `knowledgeforge.get_connections` (depth 1) to surface neighbors.
3. Summarizes the result as a graph fragment with citations.

## Troubleshooting

- `kb-mcp: command not found` → run `pip install -e kb-mcp-server/`.
- Tools missing → ensure Codex CLI was restarted after running `kf-install.sh codex`.
