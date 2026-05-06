"""Regression: conformance checks must not crash when tables lack tenant_id.

The Spanner emulator initialised from `database/spanner_schema.sdl` does NOT
have the tenant_id column on edge/entity tables (those are added by the
`add_tenant_id.ddl` migration). Conformance rules building dynamic SQL
against those tables previously failed with:

    google.api_core.exceptions.InvalidArgument: 400 Unrecognized name: tenant_id

This regression exercises the conformance flow against a Spanner emulator
DB that intentionally has NOT had the tenant migration applied. With the
fix in place, `tenant_sql_filter_for(database, table)` degrades to `TRUE`
and rules either pass or report `status=violated`, but never `status=error`
due to a missing column.
"""
from __future__ import annotations

import os
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
    database_id = f"conf-test-{uuid.uuid4().hex[:8]}"

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

    # Apply ONLY the base schema (no tenant_id migration) — this reproduces
    # the failing condition.
    import re
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

    # Reset cache so this DB is probed fresh.
    from services.tenant_context import _reset_tenant_col_cache
    _reset_tenant_col_cache()

    yield db

    try:
        db.drop()
    except Exception:
        pass


def test_conformance_does_not_error_without_tenant_column(emulator_db):
    """Conformance must complete without per-rule 'error' status from
    missing tenant_id column."""
    from services.graph_analytics import check_conformance

    report = check_conformance(emulator_db, tenant_id="demo@local")

    assert "results" in report
    assert report["total_rules"] >= 1

    # No rule should error out *because* of unrecognized tenant_id name.
    errored = [r for r in report["results"] if r["status"] == "error"]
    for r in errored:
        joined = " ".join(r.get("violations", []))
        assert "Unrecognized name: tenant_id" not in joined, (
            f"Rule {r['rule_id']} still failing on missing tenant_id column: {joined}"
        )


def test_conformance_error_result_uses_null_violation_count():
    """Errored rules should expose violation_count=None (not the legacy -1)."""
    from services.graph_analytics import check_conformance

    class _BadDB:
        def snapshot(self):
            raise RuntimeError("simulated DB outage")

    report = check_conformance(_BadDB(), tenant_id="demo@local")
    errored = [r for r in report["results"] if r["status"] == "error"]
    assert errored, "expected at least one error result against a broken DB"
    for r in errored:
        assert r["violation_count"] is None, (
            f"Rule {r['rule_id']} still uses legacy sentinel: {r['violation_count']}"
        )
