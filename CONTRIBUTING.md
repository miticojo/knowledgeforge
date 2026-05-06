# Contributing to KnowledgeForge

Thanks for your interest. KnowledgeForge is an open-source agentic knowledge platform on GCP. Contributions of any size are welcome — bug reports, docs, new retrieval strategies, ontology extensions.

## Local development

You need:
- Python 3.11+ (backend)
- Node.js 20+ (frontend)
- A GCP project with **Cloud Spanner**, **Vertex AI**, and (optional) **Cloud Run**, **Model Armor**, **Identity-Aware Proxy** enabled
- `gcloud` CLI authenticated (`gcloud auth application-default login`)

### Backend (`kb-agent`)
```bash
cd kb-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then fill the values
python main.py             # http://localhost:8080
```

### Frontend (`kb-frontend`)
```bash
cd kb-frontend
npm install
cp .env.example .env.local
npm run dev                # http://localhost:3000
```

### MCP server (`kb-mcp-server`)
```bash
pip install -e kb-mcp-server/
kb-mcp serve --backend-url http://localhost:8080
```

## Running tests

```bash
cd kb-agent && pytest tests/
cd kb-frontend && npm test
```

The `evaluation/` folder contains end-to-end retrieval benchmarks (HotpotQA, custom Q&A pairs). See `evaluation/README.md` for setup.

## Pull request guidelines

- One logical change per PR.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`).
- Update `README.md` or `docs/` if you change public behavior.
- Make sure no proprietary identifiers, secrets, or private URLs leak in:
  ```bash
  git ls-files | xargs rg -i 'AIza[0-9A-Za-z_-]{35}|sk-[A-Za-z0-9]{32,}|BEGIN (RSA|PRIVATE) KEY'
  ```
- Sign-off optional but appreciated.

## Code style

- **Python**: PEP 8, type hints on public APIs.
- **TypeScript**: project ESLint config, strict mode.
- Prefer small, composable functions over large classes.
- No dead code, no commented-out blocks. If you remove something, remove it cleanly.

## Reporting issues

Open a GitHub issue with:
1. What you expected
2. What you observed
3. Minimal reproduction (commands, sample input, env vars)

Security issues: please email the maintainers privately rather than filing a public issue.
