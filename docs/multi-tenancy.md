# Multi-Tenancy in KnowledgeForge

KnowledgeForge supports row-level multi-tenant isolation across every layer
of the stack: documents, entities, edges, chunks, and cost logs are all
tagged with a `tenant_id` and filtered on every query.

## Tenant model

A **tenant** is an opaque string. By convention we use the authenticated
user's email address (e.g. `alice@corp.com`), but any stable identifier
works.

Two reserved values exist:

| Constant                  | Value                       | Purpose                                              |
| ------------------------- | --------------------------- | ---------------------------------------------------- |
| `SHARED_ARCHISURANCE`     | `__shared__:archisurance`   | Demo dataset shipped with the project.               |
| `SHARED_HOTPOTQA`         | `__shared__:hotpotqa`       | Benchmark dataset.                                   |

The legacy `__shared__` (without dataset suffix) is still recognised for
backward compatibility but new writes should always carry a dataset suffix.

## Search scopes

Each request may set the `X-Search-Scope` header to one of:

- `mine` — only the calling tenant's rows are visible.
- `shared` — only shared dataset rows are visible (the calling tenant's
  rows are hidden).
- `all` (default) — union of `mine` and `shared`.

The active scope is translated to a SQL fragment by
`tenant_sql_filter()` in `kb-agent/services/tenant_context.py`.

## Request flow

1. The frontend reads the authenticated user's email and sets
   `X-Tenant-Id: alice@corp.com` on every request to the backend.
2. `TenantMiddleware` (in `kb-agent/main.py`) extracts the header and
   pushes it into the per-request `tenant_id` contextvar (with a
   thread-local fallback for ADK's ThreadPoolExecutor).
3. Every Spanner query built by `services/*.py` uses
   `tenant_sql_filter()` (or `tenant_sql_filter_for()` when the table
   may pre-date the migration) to inject `WHERE tenant_id IN (...)`.
4. Mutations (`graph_writer.py`) accept `tenant_id` as an explicit
   parameter and tag every row before `batch_write`.

## Cost attribution

Every API call is wrapped in a per-request `CostAccumulator`
(`services/cost_tracker.py`). On response, the `TenantMiddleware` saves
a `CostLog` row tagged with the calling `tenant_id` and the
`operation_type` (`ingestion`, `query`, or `other`).

Two endpoints expose this data:

- `GET /tenant/costs` — per-tenant rollup (all-time, last 30 days,
  per-day series).
- `GET /tenant/dashboard` — admin dashboard payload: top 10 tenants by
  cost (last 30 days), 7-day daily trend across all tenants, and the
  calling tenant's per-op-type breakdown.

## Firebase setup (production / multi-user)

1. Create a Firebase project and enable Google sign-in.
2. Copy the web app config into `kb-frontend/.env`:

   ```
   NEXT_PUBLIC_FIREBASE_API_KEY=AIza...
   NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=my-project.firebaseapp.com
   NEXT_PUBLIC_FIREBASE_PROJECT_ID=my-project
   ```

3. (Optional) Set `NEXT_PUBLIC_ALLOWED_EMAILS=alice@corp.com,bob@corp.com`
   to restrict who may sign in.
4. Restart the frontend. `AuthProvider` will detect the keys, render the
   Google sign-in screen on first visit, and propagate the signed-in
   email as `X-Tenant-Id` on every subsequent backend call.

## Dev mode (single tenant)

Leave all `NEXT_PUBLIC_FIREBASE_*` vars unset. `AuthProvider` injects a
synthetic `demo@local` user, and every backend request carries
`X-Tenant-Id: demo@local`. This is the default for local development
and CI.

## Verifying isolation

The test suite at `kb-agent/tests/test_tenant_isolation.py` exercises
every layer: context propagation, mutation tagging, query filtering,
middleware header parsing, search-scope behaviour, and the regression
guard against bare `__shared__` literals in SQL.

```
cd kb-agent
python -m pytest tests/test_tenant_isolation.py -v
```

For end-to-end verification against a real datastore, start the Spanner
emulator and run `kb-agent/scripts/init_emulator.py` to apply the
schema and tenant migration before the tests.
