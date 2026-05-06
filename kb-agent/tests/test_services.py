"""Tests for services: schema_registry, document_chunker, entity_reconciler, graph_writer.

Unit tests that do NOT require Spanner connection.
"""
import pytest
import re
from services.schema_registry import (
    ENTITY_TABLE_MAP, EDGE_TABLE_MAP, ARCHIMATE_LAYER_MAP,
    VALID_ENTITY_TYPES, VALID_RELATIONSHIP_TYPES, VALID_LAYERS,
)
from services.document_chunker import chunk_document, Chunk, _split_text_semantically
from tests.conftest import ARCHIMATE_ENTITY_TYPES, ARCHIMATE_RELATIONSHIP_TYPES


# ---------------------------------------------------------------------------
# Schema Registry tests
# ---------------------------------------------------------------------------

class TestSchemaRegistry:

    def test_all_22_entity_types_in_map(self):
        assert len(ENTITY_TABLE_MAP) == 22

    def test_all_11_relationship_types_in_map(self):
        assert len(EDGE_TABLE_MAP) == 11

    def test_entity_types_match_conftest(self):
        assert VALID_ENTITY_TYPES == ARCHIMATE_ENTITY_TYPES

    def test_relationship_types_match_conftest(self):
        assert VALID_RELATIONSHIP_TYPES == ARCHIMATE_RELATIONSHIP_TYPES

    def test_every_entity_has_required_fields(self):
        for name, info in ENTITY_TABLE_MAP.items():
            assert "table" in info, f"{name} missing 'table'"
            assert "id_col" in info, f"{name} missing 'id_col'"
            assert "name_col" in info, f"{name} missing 'name_col'"
            assert "embedding_col" in info, f"{name} missing 'embedding_col'"

    def test_every_edge_has_required_fields(self):
        for name, info in EDGE_TABLE_MAP.items():
            assert "table" in info, f"{name} missing 'table'"
            assert "detail_col" in info, f"{name} missing 'detail_col'"

    def test_every_entity_has_layer(self):
        for entity_type in VALID_ENTITY_TYPES:
            assert entity_type in ARCHIMATE_LAYER_MAP, f"{entity_type} missing from ARCHIMATE_LAYER_MAP"

    def test_layers_are_valid(self):
        expected = {"Strategy", "Business", "Application", "Technology", "Motivation"}
        assert VALID_LAYERS == expected

    def test_table_names_are_plural(self):
        """Spanner table names should be plural (e.g. ApplicationComponents not ApplicationComponent)."""
        for name, info in ENTITY_TABLE_MAP.items():
            table = info["table"]
            assert table.endswith("s") or table.endswith("es"), (
                f"Table name '{table}' for {name} should be plural"
            )

    def test_id_columns_end_with_id(self):
        for name, info in ENTITY_TABLE_MAP.items():
            assert info["id_col"].endswith("_id") or info["id_col"] == "req_id", (
                f"ID column '{info['id_col']}' for {name} should end with '_id'"
            )

    def test_embedding_columns_end_with_embedding(self):
        for name, info in ENTITY_TABLE_MAP.items():
            assert info["embedding_col"].endswith("_embedding"), (
                f"Embedding column '{info['embedding_col']}' for {name} should end with '_embedding'"
            )


# ---------------------------------------------------------------------------
# Document Chunker tests
# ---------------------------------------------------------------------------

class TestDocumentChunker:

    def test_empty_text_returns_empty(self):
        chunks = chunk_document("")
        assert chunks == []

    def test_short_text_single_chunk(self):
        chunks = chunk_document("Hello world. This is a test.")
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "text"
        assert chunks[0].chunk_index == 0

    def test_paragraphs_chunked(self):
        text = "\n\n".join([f"Paragraph {i}. " * 200 for i in range(5)])
        chunks = chunk_document(text, chunk_size=3000, overlap=300)
        assert len(chunks) >= 2

    def test_chunks_have_uuids(self):
        chunks = chunk_document("Some text content.")
        for c in chunks:
            assert len(c.chunk_id) == 36  # UUID format

    def test_chunks_have_sequential_indices(self):
        text = "\n\n".join([f"Paragraph {i}. " * 200 for i in range(10)])
        chunks = chunk_document(text, chunk_size=2000)
        for i, c in enumerate(chunks):
            assert c.chunk_index == i

    def test_image_chunks_created(self):
        chunks = chunk_document(
            "Some text",
            images=[
                {"pageNum": 1, "dataUri": "data:image/png;base64,abc123"},
                {"pageNum": 3, "dataUri": "data:image/png;base64,def456"},
            ],
        )
        image_chunks = [c for c in chunks if c.chunk_type == "image"]
        assert len(image_chunks) == 2
        assert image_chunks[0].page_number == 1
        assert image_chunks[1].page_number == 3
        assert image_chunks[0].image_uri == "data:image/png;base64,abc123"

    def test_text_and_image_chunks_mixed(self):
        chunks = chunk_document(
            "Document text content.",
            images=[{"pageNum": 1, "dataUri": "data:image/png;base64,abc"}],
        )
        text_chunks = [c for c in chunks if c.chunk_type == "text"]
        image_chunks = [c for c in chunks if c.chunk_type == "image"]
        assert len(text_chunks) >= 1
        assert len(image_chunks) == 1


class TestTextSplitting:

    def test_split_by_paragraphs(self):
        text = "Para 1.\n\nPara 2.\n\nPara 3."
        chunks = _split_text_semantically(text, chunk_size=10000, overlap=0)
        assert len(chunks) == 1  # All fit in one chunk

    def test_split_respects_chunk_size(self):
        text = "\n\n".join(["X" * 500 for _ in range(20)])
        chunks = _split_text_semantically(text, chunk_size=2000, overlap=0)
        assert len(chunks) >= 4
        for c in chunks:
            assert len(c) <= 2500  # Some slack for paragraph boundaries

    def test_overlap_present(self):
        text = "\n\n".join([f"Paragraph_{i}. " * 100 for i in range(10)])
        chunks = _split_text_semantically(text, chunk_size=2000, overlap=200)
        if len(chunks) >= 2:
            # End of chunk[0] should overlap with beginning of chunk[1]
            end_of_first = chunks[0][-100:]
            assert end_of_first in chunks[1]


# ---------------------------------------------------------------------------
# Entity Reconciler tests (unit level, no Spanner)
# ---------------------------------------------------------------------------

class TestEntityReconcilerCache:

    def test_cache_returns_same_id(self):
        from services.entity_reconciler import EntityReconciler

        class MockDB:
            def snapshot(self):
                return self
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def execute_sql(self, *a, **kw):
                return iter([])  # No matches

        reconciler = EntityReconciler(MockDB())
        id1, is_new1 = reconciler.reconcile("ApplicationComponent", "CRM", [0.1]*768)
        id2, is_new2 = reconciler.reconcile("ApplicationComponent", "CRM", [0.1]*768)
        assert id1 == id2
        assert is_new1 is True
        assert is_new2 is True  # Still True from cache (originally was new)
        assert reconciler.stats["cached"] == 1

    def test_unknown_type_creates_new(self):
        from services.entity_reconciler import EntityReconciler

        class MockDB:
            pass

        reconciler = EntityReconciler(MockDB())
        entity_id, is_new = reconciler.reconcile("UnknownType", "Test", [])
        assert is_new is True
        assert len(entity_id) == 36


# ---------------------------------------------------------------------------
# Graph Writer tests (unit level, no Spanner)
# ---------------------------------------------------------------------------

class TestGraphWriterParsing:

    def test_parse_node_format(self):
        from services.graph_writer import _NODE_RE
        m = _NODE_RE.match("ApplicationComponent:CRM System")
        assert m
        assert m.group(1) == "ApplicationComponent"
        assert m.group(2) == "CRM System"

    def test_parse_edge_format(self):
        from services.graph_writer import _EDGE_RE
        m = _EDGE_RE.match("ApplicationComponent:CRM->Serving->BusinessProcess:Order Fulfillment")
        assert m
        assert m.group(1) == "ApplicationComponent"
        assert m.group(2) == "CRM"
        assert m.group(3) == "Serving"
        assert m.group(5) == "BusinessProcess"
        assert m.group(6) == "Order Fulfillment"

    def test_parse_edge_with_qualifier(self):
        from services.graph_writer import _EDGE_RE
        m = _EDGE_RE.match("ApplicationComponent:CRM->Access[Read]->DataObject:Customer Record")
        assert m
        assert m.group(3) == "Access"
        assert m.group(4) == "Read"

    def test_parse_edge_influence_qualifier(self):
        from services.graph_writer import _EDGE_RE
        m = _EDGE_RE.match("Goal:Reduce TCO->Influence[+]->Requirement:Cloud Migration")
        assert m
        assert m.group(3) == "Influence"
        assert m.group(4) == "+"

    def test_all_entity_types_parseable(self):
        from services.graph_writer import _NODE_RE
        for entity_type in VALID_ENTITY_TYPES:
            node_str = f"{entity_type}:Test Entity"
            m = _NODE_RE.match(node_str)
            assert m, f"Failed to parse node: {node_str}"
            assert m.group(1) == entity_type

    def test_all_relationship_types_parseable(self):
        from services.graph_writer import _EDGE_RE
        for rel_type in VALID_RELATIONSHIP_TYPES:
            edge_str = f"ApplicationComponent:Src->{rel_type}->BusinessProcess:Tgt"
            m = _EDGE_RE.match(edge_str)
            assert m, f"Failed to parse edge: {edge_str}"
            assert m.group(3) == rel_type


class TestChunkMentionCorrelation:
    """Test that chunk-to-entity correlation logic works correctly."""

    def test_entity_found_in_chunk(self):
        chunks = [
            Chunk(chunk_id="c1", chunk_index=0, chunk_text="The CRM System manages customer data.", chunk_type="text"),
            Chunk(chunk_id="c2", chunk_index=1, chunk_text="Oracle Database runs on Linux servers.", chunk_type="text"),
        ]
        entities = [
            {"type": "ApplicationComponent", "name": "CRM System"},
            {"type": "SystemSoftware", "name": "Oracle Database"},
        ]

        # Simulate the chunk-mention logic from graph_writer
        mentions = []
        for c in chunks:
            text_lower = c.chunk_text.lower()
            for e in entities:
                if e["name"].lower() in text_lower:
                    mentions.append((c.chunk_id, e["type"], e["name"]))

        assert ("c1", "ApplicationComponent", "CRM System") in mentions
        assert ("c2", "SystemSoftware", "Oracle Database") in mentions
        assert len(mentions) == 2  # No cross-mentions
