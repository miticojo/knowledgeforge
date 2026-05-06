"""Regression: graph analytics endpoints must tolerate missing tenant_id.

Covers /graph/impact and helpers that build dynamic SQL with
`tenant_sql_filter_for`. Reuses the emulator fixture pattern from
test_conformance_tenant.py — same setup, separate database id.
"""
from __future__ import annotations

import os
import re
import socket
import uuid
import pytest


def _emulator_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def emulator_db():
    host = os.getenv("SPANNER_EMULATOR_HOST", "localhost:9010")
    h, p = host.split(":")
    if not _emulator_reachable(h, int(p)):
        pytest.skip(f"Spanner emulator not reachable at {host}")

    os.environ["SPANNER_EMULATOR_HOST"] = host
    from google.cloud import spanner
    from google.auth.credentials import AnonymousCredentials

    project = "demo-project"
    instance_id = "demo-instance"
    database_id = f"impact-test-{uuid.uuid4().hex[:8]}"

    client = spanner.Client(
        project=project,
        credentials=AnonymousCredentials(),
        client_options={"api_endpoint": host},
    )
    instance = client.instance(instance_id)
    if not instance.exists():
        instance = client.instance(
            instance_id,
            configuration_name=f"projects/{project}/instanceConfigs/emulator-config",
            display_name="KF Test",
            node_count=1,
        )
        instance.create().result(timeout=60)

    schema_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "database", "spanner_schema.sdl"
    )
    with open(schema_path) as f:
        ddl_text = f.read()
    cleaned = "\n".join(re.sub(r"--.*$", "", line) for line in ddl_text.splitlines())
    raw = [s.strip() for s in cleaned.split(";") if s.strip()]
    stmts = []
    for s in raw:
        head = s.lstrip().upper()
        if head.startswith("CREATE MODEL") or head.startswith("CREATE OR REPLACE MODEL"):
            continue
        if "CREATE VECTOR INDEX" in head:
            continue
        stmts.append(s)

    db = instance.database(database_id, ddl_statements=stmts)
    db.create().result(timeout=300)

    from services.tenant_context import _reset_tenant_col_cache
    _reset_tenant_col_cache()

    yield db
    try:
        db.drop()
    except Exception:
        pass


def test_impact_analysis_returns_not_found_not_sql_error(emulator_db):
    """Without tenant_id columns, impact_analysis must still execute the
    entity-lookup query (degraded filter) and return a clean 'not found'
    instead of bubbling 'Unrecognized name: tenant_id'."""
    from services.graph_analytics import impact_analysis

    result = impact_analysis(
        emulator_db,
        entity_name="DoesNotExist",
        entity_type="ApplicationComponent",
        max_hops=2,
        tenant_id="demo@local",
    )
    assert "error" in result
    assert "not found" in result["error"].lower(), (
        f"expected clean not-found error, got: {result['error']}"
    )


def test_graph_stats_does_not_raise_without_tenant_column(emulator_db):
    """get_graph_stats wraps each query in try/except, but should still
    return a well-formed payload (not error out at the top level) when the
    safe filter is in effect."""
    from services.graph_analytics import get_graph_stats

    stats = get_graph_stats(emulator_db, tenant_id="demo@local")
    for key in ("total_entities", "total_edges", "documents", "chunks"):
        assert key in stats
        assert isinstance(stats[key], int)


def test_tenant_sql_filter_for_degrades_to_true(emulator_db):
    """Direct unit check on the helper used by all the patched callers."""
    from services.tenant_context import tenant_sql_filter_for, _reset_tenant_col_cache

    _reset_tenant_col_cache()
    frag = tenant_sql_filter_for(emulator_db, "Access")
    assert frag == "TRUE", (
        f"expected degraded filter on un-migrated table, got: {frag!r}"
    )
