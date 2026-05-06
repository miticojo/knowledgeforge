# KnowledgeForge for Claude Code

## Install

```bash
# 1. Install the Python MCP server entrypoint
pip install -e kb-mcp-server/

# 2. Install the Claude Code plugin manifest
bash kf-install.sh claude
# -> ~/.claude/plugins/knowledgeforge/plugin.json

# 3. Configure backend
export BACKEND_URL=https://kb-agent-XXXX.run.app
export KF_TENANT=you@example.com   # optional
```

## Verify

Restart Claude Code, then:

```
/plugins
```

Expect: `knowledgeforge` listed. Open the plugin to confirm the 8 tools are exposed.

## Example prompt

> **User:** "What breaks downstream if I remove the BillingService component?"

**Expected agent behavior:**
1. Reads the loaded skill (`knowledgeforge-architecture`) and recognizes this as an impact question.
2. Calls `knowledgeforge.get_entity` with `name: "BillingService"` to resolve the id.
3. Calls `knowledgeforge.impact_analysis` with that entity id.
4. Returns a structured list of downstream impacted entities (services, processes, data objects), each with the source document/page citation.

## Troubleshooting

- Plugin not appearing → confirm `~/.claude/plugins/knowledgeforge/plugin.json` exists and is valid JSON (`python -m json.tool < ~/.claude/plugins/knowledgeforge/plugin.json`).
- `kb-mcp: command not found` → run `pip install -e kb-mcp-server/` in the same Python env that Claude Code's PATH sees.
