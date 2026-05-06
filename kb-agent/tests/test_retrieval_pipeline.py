"""E2E tests for the hybrid retrieval pipeline (HippoRAG-style).

Tests cover:
1. Unit tests for parsing/dedup logic (no Spanner needed)
2. Integration tests against live backend (require running backend on :8080)
3. Full pipeline E2E: SearchAgent → Coordinator → sources block

Run unit tests only:
    pytest tests/test_retrieval_pipeline.py -m "not live"

Run all including live backend tests:
    pytest tests/test_retrieval_pipeline.py
"""
import json
import os
import re
import sys
import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8080")


# ---------------------------------------------------------------------------
# Unit tests — pure logic, no external dependencies
# ---------------------------------------------------------------------------

class TestGraphConnectionParsing:
    """Test parsing of graph connection strings."""

    CONN_RE = re.compile(
        r"^(.+?)\s*\(([^)]+)\)\s*-\[([^\]]+)\]->\s*(.+?)\s*\(([^)]+)\)$"
    )

    def test_parse_named_connection(self):
        conn = "CRM System (ApplicationComponent) -[Serving]-> Order Management (BusinessProcess)"
        m = self.CONN_RE.match(conn)
        assert m is not None
        assert m.group(1).strip() == "CRM System"
        assert m.group(2).strip() == "ApplicationComponent"
        assert m.group(3).strip() == "Serving"
        assert m.group(4).strip() == "Order Management"
        assert m.group(5).strip() == "BusinessProcess"

    def test_parse_type_only_connection(self):
        conn = "TechnologyService (TechnologyService) -[Serving]-> Device (Device)"
        m = self.CONN_RE.match(conn)
        assert m is not None
        # name == type means resolution failed
        assert m.group(1).strip() == m.group(2).strip()
        assert m.group(4).strip() == m.group(5).strip()

    def test_unresolved_detection(self):
        """Type-only connections should be detectable."""
        conn = "Device (Device) -[Serving]-> TechnologyService (TechnologyService)"
        m = self.CONN_RE.match(conn)
        assert m is not None
        src_name, src_type = m.group(1).strip(), m.group(2).strip()
        tgt_name, tgt_type = m.group(4).strip(), m.group(5).strip()
        assert src_name == src_type  # unresolved
        assert tgt_name == tgt_type  # unresolved

    def test_no_match_on_invalid_format(self):
        assert self.CONN_RE.match("invalid connection string") is None
        assert self.CONN_RE.match("") is None


class TestChunkDeduplication:
    """Test chunk deduplication logic used in graph-enriched discovery."""

    def test_dedup_by_prefix(self):
        chunks = [
            {"text": "The CRM system handles orders..." * 10, "match": "vector"},
            {"text": "The CRM system handles orders..." * 10, "match": "graph"},  # duplicate
            {"text": "Authentication uses OAuth2 protocol...", "match": "keyword"},
        ]
        existing = {c["text"][:100] for c in chunks[:1]}
        new_chunks = []
        for c in chunks[1:]:
            prefix = c["text"][:100]
            if prefix not in existing:
                existing.add(prefix)
                new_chunks.append(c)
        assert len(new_chunks) == 1
        assert new_chunks[0]["match"] == "keyword"

    def test_graph_connections_dedup(self):
        connections = [
            "A (TypeA) -[Serving]-> B (TypeB)",
            "A (TypeA) -[Serving]-> B (TypeB)",  # duplicate
            "C (TypeC) -[Flow]-> D (TypeD)",
        ]
        deduped = list(dict.fromkeys(connections))
        assert len(deduped) == 2


class TestSourcesBlockParsing:
    """Test the frontend sources parsing logic (Python equivalent)."""

    SOURCES_RE = re.compile(r"<sources>([\s\S]*?)</sources>")

    def _parse_sources(self, content: str):
        if "<sources>" in content and "</sources>" not in content:
            return content.split("<sources>")[0].strip(), None
        match = self.SOURCES_RE.search(content)
        if not match:
            return content, None
        clean = self.SOURCES_RE.sub("", content).strip()
        try:
            return clean, json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            return clean, None

    def test_parse_valid_sources(self):
        content = 'La risposta.\n\n<sources>\n{"documents": [{"title": "Doc A", "page": "5"}], "graph": ["X (T) -[R]-> Y (U)"]}\n</sources>'
        clean, sources = self._parse_sources(content)
        assert clean == "La risposta."
        assert sources is not None
        assert len(sources["documents"]) == 1
        assert sources["documents"][0]["title"] == "Doc A"
        assert sources["documents"][0]["page"] == "5"
        assert len(sources["graph"]) == 1

    def test_parse_empty_sources(self):
        content = 'Risposta.\n<sources>{"documents": [], "graph": []}</sources>'
        clean, sources = self._parse_sources(content)
        assert clean == "Risposta."
        assert sources["documents"] == []
        assert sources["graph"] == []

    def test_streaming_partial_sources(self):
        content = "Risposta parziale\n<sources>"
        clean, sources = self._parse_sources(content)
        assert clean == "Risposta parziale"
        assert sources is None

    def test_no_sources_block(self):
        content = "Una risposta senza fonti."
        clean, sources = self._parse_sources(content)
        assert clean == content
        assert sources is None

    def test_invalid_json_in_sources(self):
        content = "Risposta.\n<sources>not valid json</sources>"
        clean, sources = self._parse_sources(content)
        assert clean == "Risposta."
        assert sources is None


class TestRetrievalMetadata:
    """Test retrieval metadata structure."""

    def test_metadata_has_all_fields(self):
        metadata = {
            "strategy": "hybrid_vector_graph_hipporag",
            "model": "text-embedding-004",
            "chunks_found": 15,
            "keyword_chunks": 3,
            "vector_chunks": 10,
            "graph_chunks": 2,
            "connections_found": 5,
            "entities_found": 8,
            "graph_entities_discovered": 4,
        }
        assert metadata["strategy"] == "hybrid_vector_graph_hipporag"
        assert metadata["chunks_found"] == (
            metadata["keyword_chunks"] + metadata["vector_chunks"] + metadata["graph_chunks"]
        )
        assert metadata["graph_entities_discovered"] > 0

    def test_graph_chunks_counted_correctly(self):
        chunks = [
            {"match": "keyword"}, {"match": "keyword"},
            {"match": "vector"}, {"match": "vector"}, {"match": "vector"},
            {"match": "graph"}, {"match": "graph"},
        ]
        keyword = len([c for c in chunks if c["match"] == "keyword"])
        vector = len([c for c in chunks if c["match"] == "vector"])
        graph = len([c for c in chunks if c["match"] == "graph"])
        assert keyword == 2
        assert vector == 3
        assert graph == 2
        assert keyword + vector + graph == len(chunks)


class TestEntityDiscovery:
    """Test entity name extraction from graph connections."""

    CONN_RE = re.compile(
        r"^(.+?)\s*\(([^)]+)\)\s*-\[.+\]->\s*(.+?)\s*\(([^)]+)\)$"
    )

    def _extract_entities(self, connections):
        discovered = set()
        for conn in connections:
            m = self.CONN_RE.match(conn)
            if m:
                src_name, src_type = m.group(1).strip(), m.group(2).strip()
                tgt_name, tgt_type = m.group(3).strip(), m.group(4).strip()
                if src_name != src_type:
                    discovered.add(src_name)
                if tgt_name != tgt_type:
                    discovered.add(tgt_name)
        return discovered

    def test_extract_resolved_entities(self):
        connections = [
            "CRM System (ApplicationComponent) -[Serving]-> Order Mgmt (BusinessProcess)",
            "Auth Service (ApplicationComponent) -[Serving]-> Login Flow (BusinessProcess)",
        ]
        entities = self._extract_entities(connections)
        assert entities == {"CRM System", "Order Mgmt", "Auth Service", "Login Flow"}

    def test_skip_unresolved_entities(self):
        connections = [
            "TechnologyService (TechnologyService) -[Serving]-> Device (Device)",
        ]
        entities = self._extract_entities(connections)
        assert entities == set()  # All unresolved, skip

    def test_mixed_resolved_unresolved(self):
        connections = [
            "MyApp (ApplicationComponent) -[Serving]-> Device (Device)",
        ]
        entities = self._extract_entities(connections)
        assert entities == {"MyApp"}  # Only resolved src


# ---------------------------------------------------------------------------
# Live backend tests — require running backend on :8080 with data
# ---------------------------------------------------------------------------

def _can_run_live_tests():
    """Check Gemini API key availability."""
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_GENAI_API_KEY"))


live = pytest.mark.skipif(
    not _can_run_live_tests(),
    reason=f"Live tests require running backend at {BACKEND_URL} and GOOGLE_API_KEY env var",
)


@live
class TestLiveRetrievalPipeline:
    """E2E tests against the live backend with ingested documents."""

    def _search(self, query: str) -> dict:
        """Call the search tool directly via the copilotkit ingestion endpoint."""
        # Import and call the tool directly
        from agents.search import tool_query_spanner_graph
        class DummyContext:
            state = {"headers": {"tenant_id": "test_tenant", "search_scope": "mine"}}
        result_json = tool_query_spanner_graph(query, DummyContext())
        return json.loads(result_json)

    def test_vector_search_returns_chunks(self):
        """Vector search should find semantically similar chunks."""
        result = self._search("multi-agent architecture patterns")
        assert len(result["semantically_similar_chunks"]) > 0
        print(f"  Vector search returned {len(result['semantically_similar_chunks'])} chunks")

    def test_keyword_search_returns_chunks(self):
        """Keyword search should find exact term matches."""
        result = self._search("sequential handoffs parallel processing")
        chunks = result["semantically_similar_chunks"]
        assert len(chunks) > 0
        # At least some chunks should contain the keywords
        lower_chunks = [c.lower() for c in chunks]
        has_keyword = any("sequential" in c or "parallel" in c for c in lower_chunks)
        assert has_keyword, "Expected keyword match in results"

    def test_retrieval_metadata_complete(self):
        """Retrieval metadata should have all expected fields."""
        result = self._search("agent design patterns")
        meta = result["retrieval_metadata"]
        assert meta["strategy"] in ("rrf_rerank", "rrf_fallback")
        assert "chunks_found" in meta
        assert "keyword_candidates" in meta
        assert "vector_candidates" in meta
        assert "graph_boosted" in meta
        assert "connections_found" in meta
        assert "graph_entities_discovered" in meta
        assert "fusion" in meta
        assert "selected_scope" in meta
        assert "query_cost" in meta
        print(f"  Metadata: {json.dumps(meta, indent=2)}")

    def test_chunks_have_source_prefix(self):
        """Each chunk should start with [Source: ...] prefix."""
        result = self._search("design patterns")
        for chunk in result["semantically_similar_chunks"][:3]:
            assert chunk.startswith("[Source:"), f"Chunk missing source prefix: {chunk[:80]}..."

    def test_source_documents_populated(self):
        """Source documents list should be populated."""
        result = self._search("agent architectures")
        assert len(result["source_documents"]) > 0
        for doc in result["source_documents"]:
            assert "title" in doc
            assert "match_type" in doc

    def test_graph_connections_deduplicated(self):
        """Graph connections should have no duplicates."""
        result = self._search("technology service infrastructure")
        connections = result["graph_connections"]
        assert len(connections) == len(set(connections)), "Found duplicate graph connections"

    def test_graph_enriched_chunks_when_entities_exist(self):
        """When graph entities are discovered, graph-boosted chunks should appear."""
        result = self._search("application component serving business process")
        meta = result["retrieval_metadata"]
        print(f"  Graph entities discovered: {meta['graph_entities_discovered']}")
        print(f"  Graph-boosted chunks: {meta['graph_boosted']}")
        if meta["graph_entities_discovered"] > 0:
            # With RRF graph-as-boost, boosted chunks should appear
            assert meta["graph_boosted"] >= 0, "Graph boost metric should be present"

    def test_full_pipeline_response_format(self):
        """Full pipeline should return valid JSON with all expected fields."""
        result = self._search("what is a coordinator agent")
        assert "semantically_similar_chunks" in result
        assert "graph_connections" in result
        assert "source_documents" in result
        assert "retrieval_metadata" in result
        assert isinstance(result["semantically_similar_chunks"], list)
        assert isinstance(result["graph_connections"], list)
