"""Benchmark: GQL (standalone) vs GRAPH_TABLE (SQL-embedded) on Spanner Graph.

Compares:
1. Performance (execution time per query)
2. Result equivalence (same rows returned?)
3. Feature parity (multi-hop, variable-length paths)

Run: GOOGLE_API_KEY=... GOOGLE_CLOUD_PROJECT=... SPANNER_INSTANCE=... SPANNER_DATABASE=... \
     pytest tests/test_gql_vs_graph_table.py -v -s
"""
import json
import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _can_run():
    if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("GOOGLE_GENAI_API_KEY"):
        return False
    try:
        import requests
        url = os.environ.get("BACKEND_URL", "http://127.0.0.1:8080")
        r = requests.get(f"{url}/docs", timeout=3)
        return r.status_code in (200, 404)
    except Exception:
        return False


live = pytest.mark.skipif(not _can_run(), reason="Requires API key + Spanner access")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def spanner_db():
    from services.spanner_client import get_database
    return get_database()


@pytest.fixture(scope="module")
def query_embedding():
    """Compute a reusable query embedding for all tests."""
    from services.document_chunker import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
    from google import genai
    client = genai.Client()
    emb = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents="AI Agent agentic frameworks design patterns",
        config=genai.types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    return list(emb.embeddings[0].values)


@pytest.fixture(scope="module")
def entity_table_map():
    from services.schema_registry import ENTITY_TABLE_MAP
    return ENTITY_TABLE_MAP


GRAPH_NAME = "KnowledgeGraph"
THRESHOLD = 0.5

# Entity types to test (must have both embeddings and edges)
TEST_ENTITY_TYPES = [
    ("Capability", "Capabilities", "capability_name", "capability_embedding"),
    ("ApplicationComponent", "ApplicationComponents", "app_name", "app_embedding"),
]


# ---------------------------------------------------------------------------
# Helper: timed query execution
# ---------------------------------------------------------------------------

def _timed_query(db, sql, params=None, param_types_map=None):
    """Execute a query and return (rows, elapsed_ms)."""
    from google.cloud.spanner_v1 import param_types as pt
    start = time.perf_counter()
    with db.snapshot() as snapshot:
        result = snapshot.execute_sql(
            sql,
            params=params or {},
            param_types=param_types_map or {},
        )
        rows = list(result)
    elapsed = (time.perf_counter() - start) * 1000
    return rows, elapsed


# ---------------------------------------------------------------------------
# Test: GRAPH_TABLE vs GQL — result equivalence
# ---------------------------------------------------------------------------

@live
class TestResultEquivalence:
    """Verify that GQL and GRAPH_TABLE return the same results."""

    def test_single_hop_same_results(self, spanner_db, query_embedding):
        """Single-hop traversal should return identical rows."""
        from google.cloud.spanner_v1 import param_types as pt
        emb_params = {"query_emb": query_embedding}
        emb_types = {"query_emb": pt.Array(pt.FLOAT32)}

        for etype, table, name_col, emb_col in TEST_ENTITY_TYPES:
            # GRAPH_TABLE approach (SQL-embedded)
            gt_sql = f"""
                SELECT entityName, relationType, targetType
                FROM GRAPH_TABLE(
                  {GRAPH_NAME}
                  MATCH (src:{table})-[rel]->(tgt)
                  WHERE src.{emb_col} IS NOT NULL
                    AND COSINE_DISTANCE(src.{emb_col}, @query_emb) < {THRESHOLD}
                  RETURN
                    src.{name_col} AS entityName,
                    LABELS(rel) AS relationType,
                    LABELS(tgt) AS targetType
                  LIMIT 10
                )
            """
            gt_rows, _ = _timed_query(spanner_db, gt_sql, emb_params, emb_types)

            # GQL approach (standalone)
            gql_sql = f"""
                GRAPH {GRAPH_NAME}
                MATCH (src:{table})-[rel]->(tgt)
                WHERE src.{emb_col} IS NOT NULL
                  AND COSINE_DISTANCE(src.{emb_col}, @query_emb) < {THRESHOLD}
                RETURN
                  src.{name_col} AS entityName,
                  LABELS(rel) AS relationType,
                  LABELS(tgt) AS targetType
                LIMIT 10
            """
            gql_rows, _ = _timed_query(spanner_db, gql_sql, emb_params, emb_types)

            # Compare results
            gt_set = {(r[0], str(r[1]), str(r[2])) for r in gt_rows}
            gql_set = {(r[0], str(r[1]), str(r[2])) for r in gql_rows}
            assert gt_set == gql_set, (
                f"{etype}: GRAPH_TABLE returned {len(gt_rows)} rows, "
                f"GQL returned {len(gql_rows)} rows. "
                f"Diff: GT-only={gt_set - gql_set}, GQL-only={gql_set - gt_set}"
            )
            print(f"  {etype}: {len(gt_rows)} rows — EQUIVALENT")


# ---------------------------------------------------------------------------
# Test: Performance benchmark
# ---------------------------------------------------------------------------

@live
class TestPerformanceBenchmark:
    """Compare execution times between GQL and GRAPH_TABLE."""

    N_RUNS = 3  # Average over N runs for stability

    def _benchmark(self, db, sql, params, param_types_map, n=3):
        """Run query N times, return (rows, avg_ms, min_ms, max_ms)."""
        times = []
        rows = None
        for _ in range(n):
            rows, elapsed = _timed_query(db, sql, params, param_types_map)
            times.append(elapsed)
        return rows, sum(times) / len(times), min(times), max(times)

    def test_single_hop_performance(self, spanner_db, query_embedding):
        """Compare single-hop traversal performance."""
        from google.cloud.spanner_v1 import param_types as pt
        emb_params = {"query_emb": query_embedding}
        emb_types = {"query_emb": pt.Array(pt.FLOAT32)}

        results = []
        for etype, table, name_col, emb_col in TEST_ENTITY_TYPES:
            # GRAPH_TABLE
            gt_sql = f"""
                SELECT src.{name_col}, LABELS(rel), LABELS(tgt)
                FROM GRAPH_TABLE(
                  {GRAPH_NAME}
                  MATCH (src:{table})-[rel]->(tgt)
                  WHERE src.{emb_col} IS NOT NULL
                    AND COSINE_DISTANCE(src.{emb_col}, @query_emb) < {THRESHOLD}
                  RETURN src, rel, tgt
                  LIMIT 10
                )
            """
            gt_rows, gt_avg, gt_min, gt_max = self._benchmark(
                spanner_db, gt_sql, emb_params, emb_types, self.N_RUNS
            )

            # GQL
            gql_sql = f"""
                GRAPH {GRAPH_NAME}
                MATCH (src:{table})-[rel]->(tgt)
                WHERE src.{emb_col} IS NOT NULL
                  AND COSINE_DISTANCE(src.{emb_col}, @query_emb) < {THRESHOLD}
                RETURN src.{name_col} AS entityName, LABELS(rel) AS relType, LABELS(tgt) AS tgtType
                LIMIT 10
            """
            gql_rows, gql_avg, gql_min, gql_max = self._benchmark(
                spanner_db, gql_sql, emb_params, emb_types, self.N_RUNS
            )

            results.append({
                "entity_type": etype,
                "graph_table": {"rows": len(gt_rows), "avg_ms": round(gt_avg, 1), "min": round(gt_min, 1), "max": round(gt_max, 1)},
                "gql": {"rows": len(gql_rows), "avg_ms": round(gql_avg, 1), "min": round(gql_min, 1), "max": round(gql_max, 1)},
                "speedup": round(gt_avg / gql_avg, 2) if gql_avg > 0 else None,
            })

        print("\n  === Single-hop Performance Benchmark ===")
        print(f"  {'Entity Type':<25} {'GRAPH_TABLE (ms)':<20} {'GQL (ms)':<20} {'Speedup':<10}")
        print(f"  {'-'*75}")
        for r in results:
            gt = r["graph_table"]
            gql = r["gql"]
            speedup_label = f"{r['speedup']}x" if r['speedup'] else "N/A"
            winner = "GQL" if r['speedup'] and r['speedup'] > 1 else "GRAPH_TABLE"
            print(f"  {r['entity_type']:<25} {gt['avg_ms']:>6.1f} ({gt['rows']}r)     {gql['avg_ms']:>6.1f} ({gql['rows']}r)     {speedup_label} ({winner})")

    def test_union_vs_sequential_performance(self, spanner_db, query_embedding):
        """Compare: single UNION ALL query vs sequential per-type queries."""
        from google.cloud.spanner_v1 import param_types as pt
        emb_params = {"query_emb": query_embedding}
        emb_types = {"query_emb": pt.Array(pt.FLOAT32)}

        # Approach A: Sequential queries (current production)
        start = time.perf_counter()
        total_rows_seq = 0
        for etype, table, name_col, emb_col in TEST_ENTITY_TYPES:
            sql = f"""
                GRAPH {GRAPH_NAME}
                MATCH (src:{table})-[rel]->(tgt)
                WHERE src.{emb_col} IS NOT NULL
                  AND COSINE_DISTANCE(src.{emb_col}, @query_emb) < {THRESHOLD}
                RETURN src.{name_col} AS entityName, LABELS(rel) AS relType, LABELS(tgt) AS tgtType
                LIMIT 5
            """
            rows, _ = _timed_query(spanner_db, sql, emb_params, emb_types)
            total_rows_seq += len(rows)
        sequential_ms = (time.perf_counter() - start) * 1000

        # Approach B: Single UNION ALL query
        union_parts = []
        for etype, table, name_col, emb_col in TEST_ENTITY_TYPES:
            union_parts.append(f"""
                SELECT entityName, relType, tgtType FROM
                GRAPH_TABLE(
                  {GRAPH_NAME}
                  MATCH (src:{table})-[rel]->(tgt)
                  WHERE src.{emb_col} IS NOT NULL
                    AND COSINE_DISTANCE(src.{emb_col}, @query_emb) < {THRESHOLD}
                  RETURN src.{name_col} AS entityName, LABELS(rel) AS relType, LABELS(tgt) AS tgtType
                  LIMIT 5
                )
            """)
        union_sql = "\nUNION ALL\n".join(union_parts)
        start = time.perf_counter()
        union_rows, _ = _timed_query(spanner_db, union_sql, emb_params, emb_types)
        union_ms = (time.perf_counter() - start) * 1000

        print(f"\n  === Sequential vs UNION ALL ===")
        print(f"  Sequential ({len(TEST_ENTITY_TYPES)} queries): {sequential_ms:.1f}ms, {total_rows_seq} rows")
        print(f"  UNION ALL  (1 query):          {union_ms:.1f}ms, {len(union_rows)} rows")
        print(f"  Speedup: {sequential_ms / union_ms:.2f}x" if union_ms > 0 else "  N/A")

        assert total_rows_seq == len(union_rows), (
            f"Row count mismatch: sequential={total_rows_seq}, union={len(union_rows)}"
        )


# ---------------------------------------------------------------------------
# Test: GQL-exclusive features (multi-hop, variable-length paths)
# ---------------------------------------------------------------------------

@live
class TestGQLExclusiveFeatures:
    """Test advanced GQL features not easily available in GRAPH_TABLE."""

    def test_multi_hop_traversal(self, spanner_db):
        """GQL supports multi-hop patterns natively."""
        # 2-hop: Capability -[Realization]-> ? -[Serving]-> ?
        gql_sql = f"""
            GRAPH {GRAPH_NAME}
            MATCH (a:Capabilities)-[r1]->(b)-[r2]->(c)
            RETURN
              a.capability_name AS start_entity,
              LABELS(r1) AS rel1,
              LABELS(b) AS mid_type,
              LABELS(r2) AS rel2,
              LABELS(c) AS end_type
            LIMIT 10
        """
        rows, elapsed = _timed_query(spanner_db, gql_sql)
        print(f"\n  Multi-hop (2 hops): {len(rows)} paths in {elapsed:.1f}ms")
        for row in rows[:5]:
            print(f"    Capability:{row[0]} -[{row[1]}]-> {row[2]} -[{row[3]}]-> {row[4]}")
        assert isinstance(rows, list)  # Query executed successfully

    def test_variable_length_path(self, spanner_db):
        """GQL variable-length paths: find all entities within 1-3 hops."""
        gql_sql = f"""
            GRAPH {GRAPH_NAME}
            MATCH (src:Capabilities)-[rel]->{{1,3}}(tgt)
            WHERE src.capability_name = 'Goal Setting and Monitoring'
            RETURN
              src.capability_name AS start_name,
              LABELS(tgt) AS target_type,
              COUNT(*) AS path_count
            GROUP BY start_name, target_type
            LIMIT 10
        """
        try:
            rows, elapsed = _timed_query(spanner_db, gql_sql)
            print(f"\n  Variable-length (1-3 hops from 'Goal Setting and Monitoring'):")
            print(f"  {len(rows)} target types in {elapsed:.1f}ms")
            for row in rows:
                print(f"    -> {row[1]}: {row[2]} paths")
        except Exception as e:
            # Variable-length might not be supported in all Spanner versions
            print(f"\n  Variable-length paths: NOT SUPPORTED ({type(e).__name__})")
            pytest.skip(f"Variable-length paths not supported: {e}")

    def test_bidirectional_traversal(self, spanner_db):
        """GQL bidirectional matching: find entities connected in any direction."""
        gql_sql = f"""
            GRAPH {GRAPH_NAME}
            MATCH (a:Capabilities)-[rel]-(b)
            WHERE a.capability_name = 'AI Agentic Frameworks Knowledge'
            RETURN
              a.capability_name AS entity,
              LABELS(rel) AS relation,
              LABELS(b) AS connected_type
            LIMIT 10
        """
        rows, elapsed = _timed_query(spanner_db, gql_sql)
        print(f"\n  Bidirectional from 'AI Agentic Frameworks Knowledge': {len(rows)} connections in {elapsed:.1f}ms")
        for row in rows[:5]:
            print(f"    <-[{row[1]}]-> {row[2]}")
        assert isinstance(rows, list)

    def test_gql_with_vector_similarity(self, spanner_db, query_embedding):
        """GQL + COSINE_DISTANCE: semantic graph traversal."""
        from google.cloud.spanner_v1 import param_types as pt
        gql_sql = f"""
            GRAPH {GRAPH_NAME}
            MATCH (src:Capabilities)-[rel]->(tgt)
            WHERE src.capability_embedding IS NOT NULL
              AND COSINE_DISTANCE(src.capability_embedding, @query_emb) < {THRESHOLD}
            RETURN
              src.capability_name AS source_name,
              COSINE_DISTANCE(src.capability_embedding, @query_emb) AS similarity,
              LABELS(rel) AS relation,
              LABELS(tgt) AS target_type
            ORDER BY similarity ASC
            LIMIT 10
        """
        rows, elapsed = _timed_query(
            spanner_db, gql_sql,
            {"query_emb": query_embedding},
            {"query_emb": pt.Array(pt.FLOAT32)},
        )
        print(f"\n  GQL + Vector similarity: {len(rows)} results in {elapsed:.1f}ms")
        for row in rows[:5]:
            print(f"    {row[0]} (dist={row[1]:.4f}) -[{row[2]}]-> {row[3]}")
        # Verify results are ordered by similarity
        if len(rows) >= 2:
            assert rows[0][1] <= rows[1][1], "Results should be ordered by similarity"
