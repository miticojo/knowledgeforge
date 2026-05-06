# GitHub Actions Workflows

## `ci.yml`

Runs on every push to `main` and every pull request targeting `main`.

| Job | Purpose |
| --- | --- |
| `backend-tests` | Runs the `kb-agent` pytest suite on Python 3.11. Matrix over `extras=[core, kc]`: the `kc` leg additionally installs the optional Google Knowledge Catalog extras (`pip install -e kb-agent/.[kc]`). Both legs install Tree-sitter language grammars and `sqlglot` so AST tests can execute. `tests/test_services.py` and `tests/test_tenant_isolation.py` are excluded because they have pre-existing failures (require a live Spanner emulator / fixtures not yet wired into CI) unrelated to current work. |
| `frontend-tests` | Installs `kb-frontend` deps with `npm ci` and runs `npm test` (vitest) on Node 20. |
| `secret-scan` | Greps the tracked tree with `ripgrep` for (a) common credential patterns (Google API keys, OpenAI `sk-…`, GitHub PATs, RSA/PRIVATE KEY blocks) and (b) forbidden internal branding/identifiers. Job fails if any match is found. |
| `compose-validate` | Runs `docker compose -f docker-compose.demo.yml config` to ensure the demo compose file parses and resolves cleanly. |
| `lint` | Runs `ruff check kb-agent/` for Python and `npm run lint` (if defined) for the frontend. |

All jobs run in parallel on `ubuntu-latest`.
