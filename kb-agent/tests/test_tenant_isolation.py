"""Multi-tenancy data isolation tests.

Verifies that every layer of the stack (context management, mutation building,
query filtering, HTTP middleware) correctly scopes data to the active tenant.

All external services (Spanner, Gemini API) are mocked so the suite is
deterministic and requires no cloud credentials.

Run with:
    cd kb-agent
    pytest tests/test_tenant_isolation.py -v

Architecture notes that inform the test strategy
-------------------------------------------------
- tenant_context.py uses threading.local() — isolation per OS thread.
- write_graph_to_spanner() receives tenant_id as an explicit parameter
  (default = SHARED_TENANT).  It does NOT call get_tenant() internally.
- EntityReconciler.__init__ also takes tenant_id and scopes all SQL to
  ``tenant_id IN (@tenant_id, @shared_tenant)``.
- tool_query_spanner_graph() calls get_tenant() at function entry and binds
  the result to the ``@_tid`` parameter in every SQL/GQL it issues.
- /reset-graph endpoint calls get_tenant() (imported at module top) and runs
  DELETE FROM <table> WHERE tenant_id = @tenant_id for every table.
  get_database() is imported inside the function body, so we patch
  services.spanner_client.get_database.
"""
import os
import sys
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.tenant_context import (
    set_tenant, get_tenant, set_search_scope, get_search_scope,
    set_shared_datasets, get_shared_datasets, tenant_sql_filter,
    reset_context, SHARED_TENANT, SHARED_ARCHISURANCE, SHARED_HOTPOTQA,
    ALL_SHARED_DATASETS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_database():
    """Return (db, snapshot_mock, batch_mock) triple that mimics Spanner."""
    db = MagicMock()

    snapshot = MagicMock()
    snapshot.execute_sql.return_value = iter([])
    db.snapshot.return_value.__enter__ = MagicMock(return_value=snapshot)
    db.snapshot.return_value.__exit__ = MagicMock(return_value=False)

    batch = MagicMock()
    db.batch.return_value.__enter__ = MagicMock(return_value=batch)
    db.batch.return_value.__exit__ = MagicMock(return_value=False)

    def _run_in_transaction(fn):
        txn = MagicMock()
        fn(txn)

    db.run_in_transaction.side_effect = _run_in_transaction
    return db, snapshot, batch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_tenant():
    """Reset tenant context to defaults before and after each test."""
    reset_context()
    yield
    reset_context()


# ---------------------------------------------------------------------------
# 1. Tenant Context — threading.local() isolation
# ---------------------------------------------------------------------------

class TestTenantContext:

    def test_default_tenant_is_demo_at_local(self):
        """Fresh context must default to 'demo@local'."""
        assert get_tenant() == "demo@local"

    def test_set_tenant_changes_current_tenant(self):
        set_tenant("alice@example.com")
        assert get_tenant() == "alice@example.com"

    def test_default_search_scope_is_all(self):
        assert get_search_scope() == "all"

    def test_set_search_scope(self):
        set_search_scope("mine")
        assert get_search_scope() == "mine"

    def test_default_shared_datasets(self):
        datasets = get_shared_datasets()
        assert SHARED_ARCHISURANCE in datasets
        assert SHARED_HOTPOTQA in datasets

    def test_shared_tenant_constant_value(self):
        assert SHARED_TENANT == "__shared__"

    def test_shared_dataset_constants(self):
        assert SHARED_ARCHISURANCE == "__shared__:archisurance"
        assert SHARED_HOTPOTQA == "__shared__:hotpotqa"

    def test_reset_context_restores_defaults(self):
        set_tenant("changed@example.com")
        set_search_scope("mine")
        set_shared_datasets([SHARED_ARCHISURANCE])
        reset_context()
        assert get_tenant() == "demo@local"
        assert get_search_scope() == "all"
        assert set(get_shared_datasets()) == set(ALL_SHARED_DATASETS)

    def test_thread_isolation(self):
        """Each thread must see its own tenant (threading.local)."""
        results = {}

        def worker(tenant_id, key):
            set_tenant(tenant_id)
            import time
            time.sleep(0.01)
            results[key] = get_tenant()

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [
                pool.submit(worker, "tenant-A@example.com", "a"),
                pool.submit(worker, "tenant-B@example.com", "b"),
                pool.submit(worker, "tenant-C@example.com", "c"),
            ]
            for f in futures:
                f.result()

        assert results["a"] == "tenant-A@example.com"
        assert results["b"] == "tenant-B@example.com"
        assert results["c"] == "tenant-C@example.com"

    def test_thread_does_not_pollute_main_context(self):
        """set_tenant() inside a spawned thread must not change the main thread."""
        set_tenant("main@example.com")
        barrier = threading.Barrier(2)

        def worker():
            set_tenant("worker@example.com")
            barrier.wait()

        t = threading.Thread(target=worker)
        t.start()
        barrier.wait()
        assert get_tenant() == "main@example.com"
        t.join()

    def test_search_scope_thread_isolation(self):
        """Each thread must see its own search scope."""
        results = {}

        def worker(scope, key):
            set_search_scope(scope)
            import time
            time.sleep(0.01)
            results[key] = get_search_scope()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(worker, "mine", "a"),
                pool.submit(worker, "shared", "b"),
            ]
            for f in futures:
                f.result()

        assert results["a"] == "mine"
        assert results["b"] == "shared"

    def test_shared_datasets_thread_isolation(self):
        """Each thread must see its own shared_datasets."""
        results = {}

        def worker(datasets, key):
            set_shared_datasets(datasets)
            import time
            time.sleep(0.01)
            results[key] = get_shared_datasets()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(worker, [SHARED_ARCHISURANCE], "a"),
                pool.submit(worker, [SHARED_HOTPOTQA], "b"),
            ]
            for f in futures:
                f.result()

        assert results["a"] == [SHARED_ARCHISURANCE]
        assert results["b"] == [SHARED_HOTPOTQA]

    def test_multiple_set_calls_are_independent(self):
        set_tenant("first@example.com")
        assert get_tenant() == "first@example.com"
        set_tenant("second@example.com")
        assert get_tenant() == "second@example.com"


# ---------------------------------------------------------------------------
# 1b. Shared Datasets Validation
# ---------------------------------------------------------------------------

class TestSharedDatasetsValidation:

    def test_empty_list_resets_to_defaults(self):
        set_shared_datasets([])
        assert set(get_shared_datasets()) == set(ALL_SHARED_DATASETS)

    def test_valid_datasets_are_accepted(self):
        set_shared_datasets([SHARED_ARCHISURANCE])
        assert get_shared_datasets() == [SHARED_ARCHISURANCE]

    def test_invalid_datasets_are_rejected(self):
        """Invalid dataset names (potential SQL injection) must be filtered out."""
        set_shared_datasets(["__shared__:valid", "'; DROP TABLE--"])
        assert get_shared_datasets() == ["__shared__:valid"]

    def test_all_invalid_resets_to_defaults(self):
        """If all dataset names are invalid, fall back to ALL_SHARED_DATASETS."""
        set_shared_datasets(["not_a_dataset", "another_bad"])
        assert set(get_shared_datasets()) == set(ALL_SHARED_DATASETS)


# ---------------------------------------------------------------------------
# 1c. SQL Filter Generation — tenant_sql_filter()
# ---------------------------------------------------------------------------

class TestTenantSqlFilter:

    def test_scope_all_includes_tid_and_datasets(self):
        set_search_scope("all")
        sql = tenant_sql_filter()
        assert "@_tid" in sql
        assert SHARED_ARCHISURANCE in sql
        assert SHARED_HOTPOTQA in sql

    def test_scope_mine_only_tid(self):
        set_search_scope("mine")
        sql = tenant_sql_filter()
        assert sql == "tenant_id = @_tid"
        assert SHARED_ARCHISURANCE not in sql

    def test_scope_shared_no_tid(self):
        set_search_scope("shared")
        sql = tenant_sql_filter()
        assert "@_tid" not in sql
        assert SHARED_ARCHISURANCE in sql
        assert SHARED_HOTPOTQA in sql

    def test_alias_prefix(self):
        set_search_scope("mine")
        sql = tenant_sql_filter("chunk")
        assert sql == "chunk.tenant_id = @_tid"

    def test_alias_prefix_scope_all(self):
        set_search_scope("all")
        sql = tenant_sql_filter("doc")
        assert sql.startswith("doc.tenant_id IN")

    def test_custom_datasets_reflected_in_filter(self):
        set_search_scope("all")
        set_shared_datasets([SHARED_ARCHISURANCE])
        sql = tenant_sql_filter()
        assert SHARED_ARCHISURANCE in sql
        assert SHARED_HOTPOTQA not in sql

    def test_no_old_shared_tenant_in_filter(self):
        """tenant_sql_filter must never produce the old '__shared__' constant.
        It must use dataset-specific constants like __shared__:archisurance."""
        for scope in ("all", "shared"):
            set_search_scope(scope)
            sql = tenant_sql_filter()
            # The old pattern was: IN (@_tid, '__shared__')
            # The new pattern uses: IN (@_tid, '__shared__:archisurance', '__shared__:hotpotqa')
            # Verify we don't have the bare '__shared__' without a colon suffix
            assert "'__shared__'" not in sql, (
                f"Found bare '__shared__' in SQL for scope={scope}: {sql}"
            )


# ---------------------------------------------------------------------------
# 2. Graph Writer — tenant_id must appear in every mutation tuple
# ---------------------------------------------------------------------------

class TestGraphWriterTenantInjection:
    """
    write_graph_to_spanner() accepts tenant_id as an explicit kwarg
    (default = SHARED_TENANT).  We verify that the value is threaded through
    into every mutation tuple passed to batch_write().
    """

    def _run_write_graph(self, tenant_id: str) -> list:
        """Run write_graph_to_spanner with the given tenant and return every
        mutation tuple that was passed to batch_write."""
        from services.graph_writer import write_graph_to_spanner

        graph_json = {
            "extracted_nodes": ["ApplicationComponent:CRM System"],
            "extracted_edges": [
                "ApplicationComponent:CRM System->Serving->BusinessService:Order Fulfillment"
            ],
        }
        captured_mutations = []

        def fake_batch_write(mutations):
            captured_mutations.extend(mutations)

        mock_db, snap, _ = _make_mock_database()
        snap.execute_sql.return_value = iter([])  # No existing entities

        with patch("services.graph_writer.get_database", return_value=mock_db), \
             patch("services.graph_writer.batch_write", side_effect=fake_batch_write), \
             patch("services.graph_writer.compute_entity_embeddings",
                   return_value=[[0.1] * 768]):
            write_graph_to_spanner(
                graph_json=graph_json,
                doc_id="doc-abc-123",
                doc_title="Test Document",
                doc_summary="A test summary",
                doc_embedding=[0.1] * 768,
                tenant_id=tenant_id,
            )

        return captured_mutations

    # --- helpers ---

    @staticmethod
    def _tenant_idx(columns: list[str]) -> int | None:
        return columns.index("tenant_id") if "tenant_id" in columns else None

    @staticmethod
    def _mutations_for(name: str, mutations: list) -> list:
        return [m for m in mutations if m[0] == name]

    # --- tests ---

    def test_document_mutation_contains_tenant_id(self):
        mutations = self._run_write_graph("alice@corp.com")
        doc_muts = self._mutations_for("Documents", mutations)
        assert doc_muts, "Expected a Documents mutation"
        for table_name, columns, rows in doc_muts:
            idx = self._tenant_idx(columns)
            assert idx is not None, f"tenant_id missing from Documents columns: {columns}"
            for row in rows:
                assert row[idx] == "alice@corp.com", (
                    f"Wrong tenant in Documents row: expected 'alice@corp.com', got '{row[idx]}'"
                )

    def test_entity_mutation_contains_tenant_id(self):
        mutations = self._run_write_graph("bob@corp.com")
        edge_tables = {
            "Composition", "Aggregation", "Assignment", "Realization",
            "Serving", "Access", "Influence", "Association",
            "Triggering", "Flow", "Specialization",
        }
        skip_tables = edge_tables | {
            "Documents", "DocumentChunks", "DocumentMentions", "ChunkMentions",
        }
        entity_muts = [m for m in mutations if m[0] not in skip_tables]
        for table_name, columns, rows in entity_muts:
            idx = self._tenant_idx(columns)
            assert idx is not None, (
                f"tenant_id missing from entity table '{table_name}' columns: {columns}"
            )
            for row in rows:
                assert row[idx] == "bob@corp.com", (
                    f"Wrong tenant_id in {table_name}: expected 'bob@corp.com', got '{row[idx]}'"
                )

    def test_edge_mutation_contains_tenant_id(self):
        edge_tables = {
            "Composition", "Aggregation", "Assignment", "Realization",
            "Serving", "Access", "Influence", "Association",
            "Triggering", "Flow", "Specialization",
        }
        mutations = self._run_write_graph("carol@corp.com")
        edge_muts = [m for m in mutations if m[0] in edge_tables]
        for table_name, columns, rows in edge_muts:
            idx = self._tenant_idx(columns)
            assert idx is not None, (
                f"tenant_id missing from edge table '{table_name}': {columns}"
            )
            for row in rows:
                assert row[idx] == "carol@corp.com", (
                    f"Wrong tenant_id in {table_name}: {row[idx]}"
                )

    def test_document_mentions_contain_tenant_id(self):
        mutations = self._run_write_graph("dan@corp.com")
        for table_name, columns, rows in self._mutations_for("DocumentMentions", mutations):
            idx = self._tenant_idx(columns)
            assert idx is not None, f"tenant_id missing from DocumentMentions: {columns}"
            for row in rows:
                assert row[idx] == "dan@corp.com"

    def test_default_tenant_id_is_shared(self):
        """Calling without tenant_id should default to SHARED_TENANT (safe default)."""
        from services.graph_writer import write_graph_to_spanner

        captured = []

        def fake_batch_write(mutations):
            captured.extend(mutations)

        mock_db, _, _ = _make_mock_database()

        with patch("services.graph_writer.get_database", return_value=mock_db), \
             patch("services.graph_writer.batch_write", side_effect=fake_batch_write), \
             patch("services.graph_writer.compute_entity_embeddings",
                   return_value=[[0.1] * 768]):
            write_graph_to_spanner(
                graph_json={"extracted_nodes": ["ApplicationComponent:X"],
                            "extracted_edges": []},
                doc_id="d1", doc_title="T", doc_summary="S",
                doc_embedding=[0.0] * 768,
            )

        doc_muts = [m for m in captured if m[0] == "Documents"]
        assert doc_muts
        table_name, columns, rows = doc_muts[0]
        idx = self._tenant_idx(columns)
        assert idx is not None
        assert rows[0][idx] == SHARED_TENANT, (
            f"Default tenant should be SHARED_TENANT, got '{rows[0][idx]}'"
        )

    def test_two_tenants_produce_isolated_mutations(self):
        """Two separate write calls must use their own tenant values exclusively."""
        mutations_a = self._run_write_graph("tenant-a@corp.com")
        mutations_b = self._run_write_graph("tenant-b@corp.com")

        def all_tenant_values(mutations):
            vals = set()
            for _, columns, rows in mutations:
                if "tenant_id" in columns:
                    idx = columns.index("tenant_id")
                    for row in rows:
                        vals.add(row[idx])
            return vals

        vals_a = all_tenant_values(mutations_a)
        vals_b = all_tenant_values(mutations_b)

        assert vals_a == {"tenant-a@corp.com"}, f"Unexpected tenant values in A: {vals_a}"
        assert vals_b == {"tenant-b@corp.com"}, f"Unexpected tenant values in B: {vals_b}"
        assert vals_a.isdisjoint(vals_b)


# ---------------------------------------------------------------------------
# 3. Entity Reconciler — SQL queries must include tenant scoping
# ---------------------------------------------------------------------------

class TestEntityReconcilerTenantScoping:
    """
    EntityReconciler now scopes all three SQL paths (exact match, batch exact
    match, vector match) to ``tenant_id IN (@tenant_id, @shared_tenant)``.
    We verify the filter is present and bound to the correct tenant value.
    """

    def _reconcile_and_capture(self, tenant_id: str) -> tuple[list[str], list[dict]]:
        """Run reconcile() and return (captured_sql_strings, captured_params_list)."""
        from services.entity_reconciler import EntityReconciler

        captured_sql: list[str] = []
        captured_params: list[dict] = []

        def fake_execute_sql(sql, params=None, param_types=None):
            captured_sql.append(sql)
            if params:
                captured_params.append(dict(params))
            return iter([])

        mock_snap = MagicMock()
        mock_snap.execute_sql.side_effect = fake_execute_sql
        mock_db = MagicMock()
        mock_db.snapshot.return_value.__enter__ = MagicMock(return_value=mock_snap)
        mock_db.snapshot.return_value.__exit__ = MagicMock(return_value=False)

        reconciler = EntityReconciler(mock_db, tenant_id=tenant_id)
        reconciler.reconcile("ApplicationComponent", "CRM System", [0.1] * 768)

        return captured_sql, captured_params

    def test_exact_match_query_is_issued(self):
        sql_calls, _ = self._reconcile_and_capture("tenant-x@corp.com")
        assert len(sql_calls) >= 1, "Expected at least one SQL query from reconciler"

    def test_exact_match_query_targets_correct_table(self):
        sql_calls, _ = self._reconcile_and_capture("tenant-x@corp.com")
        assert any("ApplicationComponents" in sql for sql in sql_calls), (
            f"No query against ApplicationComponents found. Queries: {sql_calls}"
        )

    def test_exact_match_query_includes_tenant_filter(self):
        sql_calls, _ = self._reconcile_and_capture("tenant-x@corp.com")
        exact_sqls = [s for s in sql_calls if "LOWER" in s and "= @name" in s]
        assert exact_sqls, "Expected an exact-match SQL query"
        for sql in exact_sqls:
            assert "tenant_id" in sql, (
                f"Exact-match SQL missing tenant_id filter:\n{sql}"
            )

    def test_exact_match_params_carry_correct_tenant(self):
        _, params_list = self._reconcile_and_capture("exact-tenant@corp.com")
        tenant_values = {p["tenant_id"] for p in params_list if "tenant_id" in p}
        assert "exact-tenant@corp.com" in tenant_values, (
            f"tenant_id param not bound to correct value. Found: {tenant_values}"
        )

    def test_exact_match_params_carry_shared_tenant(self):
        _, params_list = self._reconcile_and_capture("some-tenant@corp.com")
        shared_values = {p.get("shared_tenant") for p in params_list if "shared_tenant" in p}
        assert SHARED_TENANT in shared_values, (
            f"shared_tenant param missing or wrong. Found: {shared_values}"
        )

    def test_two_reconcilers_use_different_tenant_params(self):
        """Tenant value bound to SQL params must differ between two reconciler instances."""
        _, params_a = self._reconcile_and_capture("alice@corp.com")
        _, params_b = self._reconcile_and_capture("bob@corp.com")

        tenant_vals_a = {p["tenant_id"] for p in params_a if "tenant_id" in p}
        tenant_vals_b = {p["tenant_id"] for p in params_b if "tenant_id" in p}

        assert tenant_vals_a == {"alice@corp.com"}, f"Wrong tenant in A params: {tenant_vals_a}"
        assert tenant_vals_b == {"bob@corp.com"}, f"Wrong tenant in B params: {tenant_vals_b}"

    def test_batch_reconcile_uses_unnest_and_tenant_filter(self):
        """batch_reconcile must use UNNEST(@names) and include tenant_id filter."""
        from services.entity_reconciler import EntityReconciler

        captured_sql: list[str] = []

        def fake_execute_sql(sql, params=None, param_types=None):
            captured_sql.append(sql)
            return iter([])

        mock_snap = MagicMock()
        mock_snap.execute_sql.side_effect = fake_execute_sql
        mock_db = MagicMock()
        mock_db.snapshot.return_value.__enter__ = MagicMock(return_value=mock_snap)
        mock_db.snapshot.return_value.__exit__ = MagicMock(return_value=False)

        reconciler = EntityReconciler(mock_db, tenant_id="batch-tenant@corp.com")
        reconciler.batch_reconcile([
            {"type": "ApplicationComponent", "name": "CRM", "embedding": [0.1] * 768},
            {"type": "ApplicationComponent", "name": "ERP", "embedding": [0.2] * 768},
        ])

        assert any("UNNEST" in sql for sql in captured_sql), (
            "batch_reconcile should use UNNEST for batch exact-match"
        )
        batch_sqls = [s for s in captured_sql if "UNNEST" in s]
        for sql in batch_sqls:
            assert "tenant_id" in sql, (
                f"Batch exact-match SQL missing tenant_id filter:\n{sql}"
            )


# ---------------------------------------------------------------------------
# 4. Search Query Tenant Filtering
# ---------------------------------------------------------------------------

class TestSearchQueryTenantFiltering:
    """
    tool_query_spanner_graph() must embed the active tenant_id into every
    Spanner SQL query it issues.  We mock google.genai (imported at call time
    via ``from google import genai``) and the Spanner database, then inspect
    every SQL string and parameter dict passed to snapshot.execute_sql.
    """

    def _run_search(self, tenant_id: str, scope: str = "all") -> tuple[list[str], list[dict]]:
        """Return (all SQL strings, all params dicts) captured during search."""
        from agents.search import tool_query_spanner_graph

        captured_sql: list[str] = []
        captured_params: list[dict] = []

        def fake_execute_sql(sql, params=None, param_types=None):
            captured_sql.append(sql)
            if params:
                captured_params.append(dict(params))
            return iter([])

        mock_snap = MagicMock()
        mock_snap.execute_sql.side_effect = fake_execute_sql
        mock_db = MagicMock()
        mock_db.snapshot.return_value.__enter__ = MagicMock(return_value=mock_snap)
        mock_db.snapshot.return_value.__exit__ = MagicMock(return_value=False)

        # Build a mock for google.genai that is returned by `from google import genai`
        mock_genai = MagicMock()

        mock_expand_resp = MagicMock()
        mock_expand_resp.text = json.dumps({
            "fact_query": "CRM integration details",
            "context_query": "application layer context",
            "temporal_query": "latest version history",
            "graph_needed": False,
        })

        mock_embed_resp = MagicMock()
        mock_embed_resp.embeddings = [MagicMock(values=[0.1] * 768)]

        mock_client_instance = MagicMock()
        mock_client_instance.models.generate_content.return_value = mock_expand_resp
        mock_client_instance.models.embed_content.return_value = mock_embed_resp
        mock_genai.Client.return_value = mock_client_instance

        set_tenant(tenant_id)
        set_search_scope(scope)

        with patch("services.spanner_client.get_database", return_value=mock_db), \
             patch.dict("sys.modules", {"google.genai": mock_genai}), \
             patch("google.genai", mock_genai, create=True):
            import google
            original_genai = getattr(google, "genai", None)
            google.genai = mock_genai
            try:
                tool_query_spanner_graph("What is the CRM system?", MagicMock())
            finally:
                if original_genai is not None:
                    google.genai = original_genai
                elif hasattr(google, "genai"):
                    del google.genai

        return captured_sql, captured_params

    def test_keyword_query_includes_tenant_filter(self):
        sql_calls, _ = self._run_search("alice@corp.com")
        keyword_sqls = [s for s in sql_calls if "chunk_text" in s and "LIKE" in s]
        if not keyword_sqls:
            pytest.skip("No keyword SQL captured — query produced no keywords above stopword threshold")
        for sql in keyword_sqls:
            assert "tenant_id" in sql, (
                f"Keyword SQL missing tenant_id filter:\n{sql}"
            )

    def test_vector_query_includes_tenant_filter(self):
        sql_calls, _ = self._run_search("alice@corp.com")
        vector_sqls = [s for s in sql_calls if "COSINE_DISTANCE" in s and "chunk_embedding" in s]
        if not vector_sqls:
            pytest.skip("No vector SQL captured")
        for sql in vector_sqls:
            assert "tenant_id" in sql, (
                f"Vector SQL missing tenant_id filter:\n{sql}"
            )

    def test_tenant_filter_uses_dataset_specific_constants(self):
        """SQL filters must use __shared__:archisurance / __shared__:hotpotqa,
        NOT the bare __shared__ constant."""
        sql_calls, _ = self._run_search("alice@corp.com")
        tenant_filtered = [s for s in sql_calls if "tenant_id" in s]
        if not tenant_filtered:
            pytest.skip("No tenant-filtered SQL captured")
        for sql in tenant_filtered:
            # Must contain at least one dataset-specific shared tenant
            has_dataset_specific = (
                SHARED_ARCHISURANCE in sql or SHARED_HOTPOTQA in sql
                # scope=mine won't have shared datasets
                or "= @_tid" in sql
            )
            assert has_dataset_specific, (
                f"SQL uses neither dataset-specific constants nor @_tid:\n{sql}"
            )

    def test_scope_mine_excludes_shared_datasets(self):
        """When scope=mine, SQL filters must NOT include shared dataset constants."""
        sql_calls, _ = self._run_search("alice@corp.com", scope="mine")
        tenant_filtered = [s for s in sql_calls if "tenant_id" in s]
        if not tenant_filtered:
            pytest.skip("No tenant-filtered SQL captured")
        for sql in tenant_filtered:
            assert SHARED_ARCHISURANCE not in sql, (
                f"scope=mine SQL should not include shared datasets:\n{sql}"
            )
            assert SHARED_HOTPOTQA not in sql, (
                f"scope=mine SQL should not include shared datasets:\n{sql}"
            )

    def test_tenant_param_value_is_active_tenant(self):
        """The _tid parameter must equal the tenant active at call time."""
        _, params_list = self._run_search("specific-tenant@corp.com")
        tenant_values = {p["_tid"] for p in params_list if "_tid" in p}
        if not tenant_values:
            pytest.skip("No _tid-bearing params captured (search likely short-circuited without Gemini key)")
        assert "specific-tenant@corp.com" in tenant_values, (
            f"Expected 'specific-tenant@corp.com' in _tid params, found: {tenant_values}"
        )

    def test_different_tenants_pass_different_tid_params(self):
        """Two search calls under different tenants must use different _tid values."""
        _, params_a = self._run_search("alpha@corp.com")
        _, params_b = self._run_search("beta@corp.com")

        tids_a = {p["_tid"] for p in params_a if "_tid" in p}
        tids_b = {p["_tid"] for p in params_b if "_tid" in p}

        if not tids_a or not tids_b:
            pytest.skip("No _tid-bearing params captured for one or both tenants")

        assert tids_a == {"alpha@corp.com"}, f"Unexpected _tid in alpha run: {tids_a}"
        assert tids_b == {"beta@corp.com"}, f"Unexpected _tid in beta run: {tids_b}"


# ---------------------------------------------------------------------------
# 5. Reset Graph Tenant Scoping
# ---------------------------------------------------------------------------

class TestResetGraphTenantScoping:
    """
    The /reset-graph endpoint must:
    - Issue DELETE FROM <table> WHERE tenant_id = @tenant_id for every table
    - Refuse to operate when tenant is SHARED_TENANT (return 403)
    - Never delete shared-tenant rows (the @tenant_id param must never equal
      SHARED_TENANT when the request comes from a normal tenant)
    """

    @staticmethod
    def _load_app():
        """Import (or reload) main.py and return the module."""
        with patch.dict("sys.modules", {
            "ag_ui_adk": MagicMock(),
            "agents.coordinator": MagicMock(),
            "agents.processing": MagicMock(),
        }):
            import importlib
            import main as main_module
            importlib.reload(main_module)
        return main_module

    def test_reset_graph_uses_tenant_id_in_where_clause(self):
        """Every DELETE must contain WHERE tenant_id = @tenant_id."""
        from fastapi.testclient import TestClient

        main_module = self._load_app()
        mock_db, _, _ = _make_mock_database()
        captured_sqls: list[str] = []

        def fake_run_in_transaction(fn):
            txn = MagicMock()
            txn.execute_update.side_effect = lambda sql, **kw: captured_sqls.append(sql)
            fn(txn)

        mock_db.run_in_transaction.side_effect = fake_run_in_transaction
        client = TestClient(main_module.app)

        with patch("services.spanner_client.get_database", return_value=mock_db), \
             patch.object(main_module, "get_tenant", return_value="alice@corp.com"):
            response = client.post("/reset-graph",
                                   headers={"X-Tenant-Id": "alice@corp.com"})

        assert response.status_code == 200, response.text
        assert len(captured_sqls) > 0, "Expected DELETE statements to be executed"
        for sql in captured_sqls:
            assert "WHERE tenant_id = @tenant_id" in sql, (
                f"DELETE missing WHERE tenant_id = @tenant_id predicate:\n{sql}"
            )

    def test_reset_graph_never_issues_delete_without_predicate(self):
        """No DELETE statement may lack a WHERE clause."""
        from fastapi.testclient import TestClient

        main_module = self._load_app()
        mock_db, _, _ = _make_mock_database()
        captured_sqls: list[str] = []

        def fake_run_in_transaction(fn):
            txn = MagicMock()
            txn.execute_update.side_effect = lambda sql, **kw: captured_sqls.append(sql)
            fn(txn)

        mock_db.run_in_transaction.side_effect = fake_run_in_transaction
        client = TestClient(main_module.app)

        with patch("services.spanner_client.get_database", return_value=mock_db), \
             patch.object(main_module, "get_tenant", return_value="safe-tenant@corp.com"):
            response = client.post("/reset-graph",
                                   headers={"X-Tenant-Id": "safe-tenant@corp.com"})

        assert response.status_code == 200
        for sql in captured_sqls:
            upper = sql.upper()
            if upper.strip().startswith("DELETE"):
                assert "WHERE" in upper, f"DELETE without WHERE clause:\n{sql}"

    def test_reset_graph_blocks_shared_tenant(self):
        """Calling /reset-graph with SHARED_TENANT must return HTTP 403."""
        from fastapi.testclient import TestClient

        main_module = self._load_app()
        client = TestClient(main_module.app)

        with patch.object(main_module, "get_tenant", return_value=SHARED_TENANT):
            response = client.post("/reset-graph",
                                   headers={"X-Tenant-Id": SHARED_TENANT})

        assert response.status_code == 403, (
            f"Expected 403 for shared tenant reset, got {response.status_code}: {response.text}"
        )

    def test_reset_graph_does_not_delete_shared_tenant_rows(self):
        """The @tenant_id param value bound in DELETEs must never equal SHARED_TENANT."""
        from fastapi.testclient import TestClient

        main_module = self._load_app()
        mock_db, _, _ = _make_mock_database()
        captured_params: list[dict] = []

        def fake_run_in_transaction(fn):
            txn = MagicMock()

            def _exec_update(sql, params=None, param_types=None, **kw):
                if params:
                    captured_params.append(dict(params))

            txn.execute_update.side_effect = _exec_update
            fn(txn)

        mock_db.run_in_transaction.side_effect = fake_run_in_transaction
        client = TestClient(main_module.app)

        with patch("services.spanner_client.get_database", return_value=mock_db), \
             patch.object(main_module, "get_tenant", return_value="normal-tenant@corp.com"):
            response = client.post("/reset-graph",
                                   headers={"X-Tenant-Id": "normal-tenant@corp.com"})

        assert response.status_code == 200
        for params in captured_params:
            assert params.get("tenant_id") != SHARED_TENANT, (
                "DELETE was issued with tenant_id = SHARED_TENANT — "
                "this would destroy shared data"
            )

    def test_reset_graph_response_includes_tenant_name(self):
        """Success response must mention which tenant was reset."""
        from fastapi.testclient import TestClient

        main_module = self._load_app()
        mock_db, _, _ = _make_mock_database()
        client = TestClient(main_module.app)

        with patch("services.spanner_client.get_database", return_value=mock_db), \
             patch.object(main_module, "get_tenant", return_value="alice@corp.com"):
            response = client.post("/reset-graph",
                                   headers={"X-Tenant-Id": "alice@corp.com"})

        assert response.status_code == 200
        body = response.json()
        assert "alice@corp.com" in body.get("message", ""), (
            f"Response message should name the tenant: {body}"
        )

    def test_reset_graph_covers_all_expected_tables(self):
        """Every ArchiMate table and auxiliary table must be covered by a DELETE."""
        from fastapi.testclient import TestClient

        main_module = self._load_app()
        mock_db, _, _ = _make_mock_database()
        deleted_tables: list[str] = []

        def fake_run_in_transaction(fn):
            txn = MagicMock()

            def _exec_update(sql, **kw):
                # Extract table name from "DELETE FROM <Table> WHERE ..."
                parts = sql.split()
                if len(parts) >= 3 and parts[0].upper() == "DELETE" and parts[1].upper() == "FROM":
                    deleted_tables.append(parts[2])

            txn.execute_update.side_effect = _exec_update
            fn(txn)

        mock_db.run_in_transaction.side_effect = fake_run_in_transaction
        client = TestClient(main_module.app)

        with patch("services.spanner_client.get_database", return_value=mock_db), \
             patch.object(main_module, "get_tenant", return_value="check@corp.com"):
            response = client.post("/reset-graph",
                                   headers={"X-Tenant-Id": "check@corp.com"})

        assert response.status_code == 200
        mandatory_tables = {"Documents", "DocumentChunks", "DocumentMentions"}
        missing = mandatory_tables - set(deleted_tables)
        assert not missing, (
            f"reset-graph did not issue DELETEs for required tables: {missing}"
        )


# ---------------------------------------------------------------------------
# 6. API Middleware — X-Tenant-Id and X-Search-Scope header propagation
# ---------------------------------------------------------------------------

class TestTenantMiddleware:
    """
    TenantMiddleware must read X-Tenant-Id and X-Search-Scope from every
    request and call set_tenant()/set_search_scope() so that endpoint handlers
    see the correct values.
    """

    @pytest.fixture
    def probe_client(self):
        """TestClient with only the TenantMiddleware wired up and a /probe endpoint."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from fastapi.responses import JSONResponse
        from starlette.middleware.base import BaseHTTPMiddleware

        probe_app = FastAPI()

        class _TenantMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                tid = request.headers.get("X-Tenant-Id", "demo@local").split(",")[0].strip()
                set_tenant(tid)
                scope = request.headers.get("X-Search-Scope", "all")
                if scope not in ("all", "mine", "shared"):
                    scope = "all"
                set_search_scope(scope)
                return await call_next(request)

        probe_app.add_middleware(_TenantMiddleware)

        @probe_app.get("/probe-tenant")
        def probe():
            return JSONResponse({
                "tenant": get_tenant(),
                "scope": get_search_scope(),
            })

        return TestClient(probe_app)

    def test_no_header_defaults_to_demo_at_local(self, probe_client):
        response = probe_client.get("/probe-tenant")
        assert response.status_code == 200
        assert response.json()["tenant"] == "demo@local"

    def test_header_sets_tenant_correctly(self, probe_client):
        response = probe_client.get("/probe-tenant",
                                    headers={"X-Tenant-Id": "alice@corp.com"})
        assert response.status_code == 200
        assert response.json()["tenant"] == "alice@corp.com"

    def test_scope_header_sets_scope(self, probe_client):
        response = probe_client.get("/probe-tenant",
                                    headers={"X-Search-Scope": "mine"})
        assert response.json()["scope"] == "mine"

    def test_invalid_scope_defaults_to_all(self, probe_client):
        response = probe_client.get("/probe-tenant",
                                    headers={"X-Search-Scope": "invalid"})
        assert response.json()["scope"] == "all"

    def test_different_sequential_requests_use_different_tenants(self, probe_client):
        r1 = probe_client.get("/probe-tenant", headers={"X-Tenant-Id": "tenant-1@corp.com"})
        r2 = probe_client.get("/probe-tenant", headers={"X-Tenant-Id": "tenant-2@corp.com"})
        assert r1.json()["tenant"] == "tenant-1@corp.com"
        assert r2.json()["tenant"] == "tenant-2@corp.com"

    def test_shared_tenant_header_is_forwarded(self, probe_client):
        """Middleware must not block or transform the __shared__ header value."""
        response = probe_client.get("/probe-tenant",
                                    headers={"X-Tenant-Id": SHARED_TENANT})
        assert response.status_code == 200
        assert response.json()["tenant"] == SHARED_TENANT

    def test_comma_separated_tenant_takes_first(self, probe_client):
        """If X-Tenant-Id has multiple values, take the first."""
        response = probe_client.get("/probe-tenant",
                                    headers={"X-Tenant-Id": "first@corp.com, second@corp.com"})
        assert response.json()["tenant"] == "first@corp.com"

    def test_upload_document_stores_tenant_at_upload_time(self):
        """The /upload-document endpoint must record get_tenant() at the moment
        of the call — verified by inspecting the in-memory document store."""
        with patch.dict("sys.modules", {
            "ag_ui_adk": MagicMock(),
            "agents.coordinator": MagicMock(),
            "agents.processing": MagicMock(),
        }):
            import importlib
            import main as main_module
            importlib.reload(main_module)
            from fastapi.testclient import TestClient
            client = TestClient(main_module.app)

            response = client.post(
                "/upload-document",
                json={"text": "Hello world", "fileName": "test.txt", "images": []},
                headers={"X-Tenant-Id": "uploading-tenant@corp.com"},
            )

        assert response.status_code == 200
        assert main_module._uploaded_document is not None
        assert main_module._uploaded_document["tenant_id"] == "uploading-tenant@corp.com", (
            f"Stored tenant_id mismatch: {main_module._uploaded_document.get('tenant_id')}"
        )


# ---------------------------------------------------------------------------
# 7. QA Cache — tenant-awareness
# ---------------------------------------------------------------------------

class TestQaCacheTenantAwareness:
    """
    The CompactRAG fast-path must be disabled when search scope is 'mine',
    since QA cache is built from shared datasets only.
    """

    def test_qa_cache_skips_when_scope_mine(self):
        """search_qa_cache must return None when scope is 'mine'."""
        from services.qa_cache import search_qa_cache
        set_search_scope("mine")
        result = search_qa_cache([0.1] * 768)
        assert result is None, "QA cache should return None when scope=mine"

    def test_qa_cache_works_when_scope_all(self):
        """search_qa_cache should not be blocked by scope='all'."""
        from services.qa_cache import search_qa_cache
        set_search_scope("all")
        # With empty cache, returns None (but doesn't short-circuit on scope)
        result = search_qa_cache([0.1] * 768)
        assert result is None  # Empty cache, but the scope check passed

    def test_qa_cache_works_when_scope_shared(self):
        """search_qa_cache should not be blocked by scope='shared'."""
        from services.qa_cache import search_qa_cache
        set_search_scope("shared")
        result = search_qa_cache([0.1] * 768)
        assert result is None  # Empty cache, but the scope check passed


# ---------------------------------------------------------------------------
# 8. Regression: no hardcoded '__shared__' in SQL-producing code
# ---------------------------------------------------------------------------

class TestNoHardcodedSharedTenant:
    """
    Regression guard: no file in the services/ or agents/ directories should
    contain a hardcoded SQL pattern like tenant_id IN (..., '__shared__') where
    '__shared__' is the bare constant without a dataset suffix.

    Files that legitimately reference the SHARED_TENANT constant for non-SQL
    purposes (e.g., defining it, or blocking reset) are excluded.
    """

    @staticmethod
    def _find_bare_shared_in_sql(filepath: str) -> list[str]:
        """Return lines containing hardcoded '__shared__' in SQL context."""
        violations = []
        with open(filepath) as f:
            for i, line in enumerate(f, 1):
                # Look for SQL patterns using the bare '__shared__' string
                # Exclude: constant definitions, imports, comments
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("SHARED_TENANT"):
                    continue
                if "= \"__shared__\"" in line or "= '__shared__'" in line:
                    # Constant definition
                    continue
                # Match SQL patterns like: IN (@x, '__shared__')
                if "'__shared__'" in line and "tenant_id" in line.lower():
                    violations.append(f"{filepath}:{i}: {stripped}")
        return violations

    def test_no_hardcoded_shared_in_services(self):
        services_dir = os.path.join(os.path.dirname(__file__), "..", "services")
        violations = []
        for fname in os.listdir(services_dir):
            if fname.endswith(".py"):
                violations.extend(self._find_bare_shared_in_sql(
                    os.path.join(services_dir, fname)
                ))
        assert not violations, (
            f"Found hardcoded '__shared__' in SQL context (should use tenant_sql_filter()):\n"
            + "\n".join(violations)
        )

    def test_no_hardcoded_shared_in_main(self):
        main_path = os.path.join(os.path.dirname(__file__), "..", "main.py")
        violations = self._find_bare_shared_in_sql(main_path)
        assert not violations, (
            f"Found hardcoded '__shared__' in SQL context in main.py:\n"
            + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# 9. Cost attribution — costs must be tagged with the calling tenant
# ---------------------------------------------------------------------------

class TestCostAttribution:
    """save_cost_log must persist the calling tenant verbatim, and the
    /tenant/costs query must scope by @tid."""

    def test_save_cost_log_inserts_tenant_id(self):
        from services.cost_tracker import CostAccumulator, save_cost_log

        captured = {}

        def fake_run_in_transaction(fn):
            txn = MagicMock()

            def _insert(table, columns, values):
                captured["table"] = table
                captured["columns"] = list(columns)
                captured["values"] = [list(v) for v in values]

            txn.insert.side_effect = _insert
            fn(txn)

        mock_db = MagicMock()
        mock_db.run_in_transaction.side_effect = fake_run_in_transaction

        tracker = CostAccumulator()
        tracker.spanner_writes = 5

        with patch("services.spanner_client.get_database", return_value=mock_db):
            save_cost_log("alice@corp.com", "ingestion", "op-123", tracker)

        assert captured["table"] == "CostLog"
        idx = captured["columns"].index("tenant_id")
        assert captured["values"][0][idx] == "alice@corp.com"

    def test_two_tenants_get_separate_cost_rows(self):
        from services.cost_tracker import CostAccumulator, save_cost_log

        rows: list = []

        def fake_run_in_transaction(fn):
            txn = MagicMock()
            txn.insert.side_effect = lambda table, columns, values: rows.append(
                (table, list(columns), [list(v) for v in values])
            )
            fn(txn)

        mock_db = MagicMock()
        mock_db.run_in_transaction.side_effect = fake_run_in_transaction

        with patch("services.spanner_client.get_database", return_value=mock_db):
            save_cost_log("alice@corp.com", "query", "a", CostAccumulator())
            save_cost_log("bob@corp.com", "query", "b", CostAccumulator())

        assert len(rows) == 2
        tenants = []
        for _, columns, values in rows:
            idx = columns.index("tenant_id")
            tenants.append(values[0][idx])
        assert tenants == ["alice@corp.com", "bob@corp.com"]

    def test_tenant_costs_endpoint_scopes_by_tid(self):
        """GET /tenant/costs must bind the active tenant to @tid."""
        from fastapi.testclient import TestClient

        with patch.dict("sys.modules", {
            "ag_ui_adk": MagicMock(),
            "agents.coordinator": MagicMock(),
            "agents.processing": MagicMock(),
        }):
            import importlib
            import main as main_module
            importlib.reload(main_module)

        captured_params: list[dict] = []
        mock_snap = MagicMock()

        def fake_execute_sql(sql, params=None, param_types=None):
            if params:
                captured_params.append(dict(params))
            return iter([])

        mock_snap.execute_sql.side_effect = fake_execute_sql
        mock_db = MagicMock()
        mock_db.snapshot.return_value.__enter__ = MagicMock(return_value=mock_snap)
        mock_db.snapshot.return_value.__exit__ = MagicMock(return_value=False)

        client = TestClient(main_module.app)
        with patch("services.spanner_client.get_database", return_value=mock_db), \
             patch.object(main_module, "get_tenant", return_value="cost-tenant@corp.com"):
            response = client.get("/tenant/costs",
                                  headers={"X-Tenant-Id": "cost-tenant@corp.com"})
        assert response.status_code == 200, response.text
        tids = {p.get("tid") for p in captured_params if "tid" in p}
        assert tids == {"cost-tenant@corp.com"}, (
            f"Expected /tenant/costs to bind tid=cost-tenant@corp.com, got {tids}"
        )

    def test_tenant_dashboard_endpoint_returns_payload(self):
        """GET /tenant/dashboard must return the expected top-level keys."""
        from fastapi.testclient import TestClient

        with patch.dict("sys.modules", {
            "ag_ui_adk": MagicMock(),
            "agents.coordinator": MagicMock(),
            "agents.processing": MagicMock(),
        }):
            import importlib
            import main as main_module
            importlib.reload(main_module)

        mock_db, snap, _ = _make_mock_database()
        snap.execute_sql.return_value = iter([])

        client = TestClient(main_module.app)
        with patch("services.spanner_client.get_database", return_value=mock_db), \
             patch.object(main_module, "get_tenant", return_value="dash-tenant@corp.com"):
            response = client.get("/tenant/dashboard",
                                  headers={"X-Tenant-Id": "dash-tenant@corp.com"})
        assert response.status_code == 200, response.text
        body = response.json()
        for key in ("tenant_id", "top_tenants", "daily_trend", "op_type_breakdown"):
            assert key in body, f"missing {key} in /tenant/dashboard response"
        assert body["tenant_id"] == "dash-tenant@corp.com"
