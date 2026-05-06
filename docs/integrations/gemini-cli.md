# KnowledgeForge for Gemini CLI

## Install

```bash
# 1. Install the Python MCP server entrypoint
pip install -e kb-mcp-server/

# 2. Install the Gemini extension manifest
bash kf-install.sh gemini
# -> ~/.gemini/extensions/knowledgeforge/gemini-extension.json

# 3. Configure backend
export BACKEND_URL=https://kb-agent-XXXX.run.app
export KF_TENANT=you@example.com   # optional
```

Alternative (without the installer): `gemini extensions install file://$(pwd)`.

## Verify

```bash
gemini /mcp
# Expect: "knowledgeforge" listed with 8 tools.
```

## Example prompt

> **User:** "Give me a knowledge brief and then list the top 5 god nodes."

**Expected agent behavior:**
1. Calls `knowledgeforge.get_brief` → returns layer/doc/entity counts.
2. Calls `knowledgeforge.god_nodes` with `limit: 5` → returns the most connected hubs.
3. Synthesizes a 1-paragraph summary citing the hubs by name.

## Troubleshooting

- `kb-mcp: command not found` → run `pip install -e kb-mcp-server/`.
- Tools return "backend unreachable" → check `BACKEND_URL` is exported in the shell that launched Gemini CLI.
- Multi-tenant data not visible → set `KF_TENANT` to the same email used at ingestion.
