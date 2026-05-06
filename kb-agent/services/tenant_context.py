"""Tenant context for multi-tenancy.

Uses contextvars as primary storage (propagated by Starlette/anyio from async
middleware to sync endpoint handlers) with module-global fallbacks for ADK's
ThreadPoolExecutor which does NOT propagate contextvars.

Thread-safety note: the global fallbacks are safe ONLY when Cloud Run is
deployed with max-concurrency=1 (one request at a time per instance).
The contextvars path is always thread-safe.
"""
import re
from contextvars import ContextVar

SHARED_TENANT = "__shared__"  # legacy, kept for compatibility
SHARED_ARCHISURANCE = "__shared__:archisurance"
SHARED_HOTPOTQA = "__shared__:hotpotqa"
ALL_SHARED_DATASETS = [SHARED_ARCHISURANCE, SHARED_HOTPOTQA]

# Safe pattern for dataset identifiers (prevents SQL injection)
_SAFE_DATASET_RE = re.compile(r"^__shared__:[a-z0-9_]+$")

# Primary: contextvars (propagated by Starlette async→sync, asyncio.to_thread)
_tenant_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)
_scope_var: ContextVar[str | None] = ContextVar("search_scope", default=None)
_datasets_var: ContextVar[list[str] | None] = ContextVar("shared_datasets", default=None)
_entity_scope_var: ContextVar[list[str]] = ContextVar("entity_scope", default=[])

# Fallback: module globals for ADK ThreadPoolExecutor (no contextvar propagation).
# Safe only with Cloud Run max-concurrency=1.
_fallback_tenant: str = "demo@local"
_fallback_scopes: dict[str, str] = {}
_fallback_datasets: list[str] = list(ALL_SHARED_DATASETS)
_fallback_entity_scope: list[str] = []



def set_tenant(tenant_id: str, update_fallback: bool = True) -> None:
    """Set the current tenant for this request."""
    global _fallback_tenant
    _tenant_var.set(tenant_id)
    if update_fallback:
        _fallback_tenant = tenant_id


def get_tenant() -> str:
    """Get the current tenant ID."""
    val = _tenant_var.get(None)
    return val if val is not None else _fallback_tenant


def set_search_scope(scope: str) -> None:
    """Set the search scope for this request."""
    global _fallback_scopes
    _scope_var.set(scope)
    tid = get_tenant()
    _fallback_scopes[tid] = scope


def get_search_scope() -> str:
    """Get the current search scope."""
    val = _scope_var.get(None)
    if val is not None:
        return val
    tid = get_tenant()
    return _fallback_scopes.get(tid, "all")



def set_shared_datasets(datasets: list[str]) -> None:
    """Set which shared datasets to include in search.

    Only accepts dataset identifiers matching __shared__:<name> pattern.
    Falls back to ALL_SHARED_DATASETS if list is empty or contains invalid values.
    """
    global _fallback_datasets
    if datasets:
        safe = [d for d in datasets if _SAFE_DATASET_RE.match(d)]
        resolved = safe if safe else list(ALL_SHARED_DATASETS)
    else:
        resolved = list(ALL_SHARED_DATASETS)
    _datasets_var.set(resolved)
    _fallback_datasets = resolved


def get_shared_datasets() -> list[str]:
    """Get the currently active shared dataset tenant IDs."""
    val = _datasets_var.get(None)
    return val if val is not None else list(_fallback_datasets)


def tenant_sql_filter(alias: str = "") -> str:
    """Return SQL WHERE clause fragment based on current scope and datasets.

    Uses @_tid as the bind parameter for the current tenant ID.
    Shared dataset IDs are interpolated as string literals but validated
    against _SAFE_DATASET_RE to prevent injection.
    """
    scope = get_search_scope()
    prefix = f"{alias}." if alias else ""
    if scope == "mine":
        return f"{prefix}tenant_id = @_tid"
    elif scope == "shared":
        datasets = get_shared_datasets()
        quoted = ", ".join(f"'{d}'" for d in datasets if _SAFE_DATASET_RE.match(d))
        if not quoted:
            quoted = f"'{SHARED_ARCHISURANCE}', '{SHARED_HOTPOTQA}'"
        return f"{prefix}tenant_id IN ({quoted})"
    else:
        datasets = get_shared_datasets()
        quoted = ", ".join(f"'{d}'" for d in datasets if _SAFE_DATASET_RE.match(d))
        if not quoted:
            quoted = f"'{SHARED_ARCHISURANCE}', '{SHARED_HOTPOTQA}'"
        return f"{prefix}tenant_id IN (@_tid, {quoted})"


# ---------------------------------------------------------------------------
# tenant_id column existence cache
# ---------------------------------------------------------------------------
# Some Spanner databases (notably the emulator initialised from the base
# spanner_schema.sdl, before the add_tenant_id.ddl migration runs) do not
# yet have the tenant_id column on every table. Building queries that
# reference tenant_id against such tables fails with:
#   "Unrecognized name: tenant_id"
# breaking conformance checks, impact analysis, and /tenant/stats.
#
# We cache the per-(database, table) presence of tenant_id on first probe
# so callers can degrade gracefully (skip filter) without per-query DDL
# round-trips. Cache is keyed by id(database) so multiple databases coexist
# safely; each entry is a dict[str -> bool].
_tenant_col_cache: dict[int, dict[str, bool]] = {}


def _has_tenant_id_column(database, table: str) -> bool:
    """Return True if `table` has a tenant_id column on this database.

    Result is cached per-(database, table). Probe failures are cached as
    False (conservative: we'd rather skip the filter than crash the query).
    """
    db_key = id(database)
    table_cache = _tenant_col_cache.setdefault(db_key, {})
    if table in table_cache:
        return table_cache[table]
    try:
        with database.snapshot() as snap:
            rows = list(snap.execute_sql(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = @t AND column_name = 'tenant_id'",
                params={"t": table},
                param_types=_string_param_type_map(),
            ))
            present = len(rows) > 0
    except Exception:
        present = False
    table_cache[table] = present
    return present


def _string_param_type_map() -> dict:
    from google.cloud.spanner_v1 import param_types
    return {"t": param_types.STRING}


def tenant_sql_filter_for(database, table: str, alias: str = "") -> str:
    """Like `tenant_sql_filter`, but degrades to `TRUE` when the target
    table has no tenant_id column on this database.

    Use this anywhere a query is built dynamically against a table that
    may or may not have been migrated. The returned fragment is always
    safe to interpolate after `WHERE` / `AND`.
    """
    if not _has_tenant_id_column(database, table):
        return "TRUE"
    return tenant_sql_filter(alias=alias)


def _reset_tenant_col_cache() -> None:
    """Test hook: clear the tenant_id column-presence cache."""
    _tenant_col_cache.clear()


def set_entity_scope(ids: list[str]) -> None:
    """Set the active entity-scope (list of entity_ids) for this request.

    Empty list means "no scope filter". Mirrors the contextvar+global fallback
    pattern used for tenant/search-scope so ADK ThreadPoolExecutor threads can
    still observe the value.
    """
    global _fallback_entity_scope
    safe = [i.strip() for i in (ids or []) if i and i.strip()]
    _entity_scope_var.set(safe)
    _fallback_entity_scope = safe


def get_entity_scope() -> list[str]:
    """Return the current entity-scope, or [] when none is set."""
    val = _entity_scope_var.get(None)
    if val is not None:
        return val
    return list(_fallback_entity_scope)


def reset_context() -> None:
    """Reset all tenant context to defaults. Useful for testing."""
    global _fallback_tenant, _fallback_scopes, _fallback_datasets, _fallback_entity_scope
    _fallback_tenant = "demo@local"
    _fallback_scopes = {}
    _fallback_datasets = list(ALL_SHARED_DATASETS)
    _fallback_entity_scope = []
    # Reset contextvars to None (will fall back to globals)
    _tenant_var.set(None)
    _scope_var.set(None)
    _datasets_var.set(None)
    _entity_scope_var.set([])

