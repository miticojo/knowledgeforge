"""
Test Suite 1: Ontology Compliance
Validates that ontology.yaml defines all ArchiMate 3.2 Wave 2 entities and relationships
correctly, and that the dynamic Pydantic model generation works.
"""
import pytest
import yaml
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import (
    ARCHIMATE_ENTITY_TYPES,
    ARCHIMATE_RELATIONSHIP_TYPES,
    ARCHIMATE_LAYERS,
    ENTITY_LAYER_MAP,
)


class TestOntologyYAMLStructure:
    """Validate the YAML schema has all required sections and entities."""

    def test_yaml_loads_without_error(self, ontology_data):
        assert ontology_data is not None
        assert isinstance(ontology_data, dict)

    def test_has_entities_section(self, ontology_data):
        assert "entities" in ontology_data, "ontology.yaml must have an 'entities' section"

    def test_has_extracted_entities_section(self, ontology_data):
        assert "extracted_entities" in ontology_data, (
            "ontology.yaml must have an 'extracted_entities' root object"
        )

    def test_has_relationships_section(self, ontology_data):
        assert "relationships" in ontology_data, (
            "ontology.yaml must define a 'relationships' section with ArchiMate relationship types"
        )

    def test_all_22_entity_types_present(self, ontology_data):
        defined = set(ontology_data["entities"].keys())
        missing = ARCHIMATE_ENTITY_TYPES - defined
        assert not missing, f"Missing entity types in ontology.yaml: {missing}"

    def test_no_extra_entity_types(self, ontology_data):
        """Entities must be strict ArchiMate types — no custom/generic types."""
        defined = set(ontology_data["entities"].keys())
        # Allow ExtractedRelationship as a helper type
        allowed_extras = {"ExtractedRelationship"}
        extra = defined - ARCHIMATE_ENTITY_TYPES - allowed_extras
        assert not extra, f"Non-ArchiMate entity types found: {extra}"

    def test_all_11_relationship_types_present(self, ontology_data):
        defined = set(ontology_data["relationships"].keys())
        missing = ARCHIMATE_RELATIONSHIP_TYPES - defined
        assert not missing, f"Missing relationship types: {missing}"

    def test_no_extra_relationship_types(self, ontology_data):
        defined = set(ontology_data["relationships"].keys())
        extra = defined - ARCHIMATE_RELATIONSHIP_TYPES
        assert not extra, f"Non-ArchiMate relationship types found: {extra}"


class TestEntityFieldCompleteness:
    """Every entity must have required fields for graph DB storage."""

    REQUIRED_FIELDS_ALL = {"description", "archimate_layer", "source_doc_id"}

    def test_every_entity_has_description(self, ontology_data):
        for name, entity in ontology_data["entities"].items():
            if name == "ExtractedRelationship":
                continue
            fields = set(entity.get("fields", {}).keys())
            assert "description" in fields, (
                f"Entity '{name}' is missing a 'description' field"
            )

    def test_every_entity_has_archimate_layer(self, ontology_data):
        for name, entity in ontology_data["entities"].items():
            if name == "ExtractedRelationship":
                continue
            fields = set(entity.get("fields", {}).keys())
            assert "archimate_layer" in fields, (
                f"Entity '{name}' is missing 'archimate_layer' field"
            )

    def test_every_entity_has_source_doc_id(self, ontology_data):
        for name, entity in ontology_data["entities"].items():
            if name == "ExtractedRelationship":
                continue
            fields = set(entity.get("fields", {}).keys())
            assert "source_doc_id" in fields, (
                f"Entity '{name}' is missing 'source_doc_id' field"
            )

    def test_every_entity_has_id_field(self, ontology_data):
        """Each entity must have a primary key field ending with _id."""
        for name, entity in ontology_data["entities"].items():
            if name == "ExtractedRelationship":
                continue
            fields = entity.get("fields", {})
            id_fields = [f for f in fields if f.endswith("_id") and f != "source_doc_id"]
            assert id_fields, f"Entity '{name}' has no primary key *_id field"

    def test_every_entity_has_name_field(self, ontology_data):
        """Each entity must have a human-readable name field."""
        for name, entity in ontology_data["entities"].items():
            if name == "ExtractedRelationship":
                continue
            fields = entity.get("fields", {})
            name_fields = [f for f in fields if f.endswith("_name") or f == "title"]
            assert name_fields, f"Entity '{name}' has no *_name or title field"

    def test_entity_descriptions_reference_archimate(self, ontology_data):
        """Each entity description should mention 'ArchiMate' for clarity."""
        for name, entity in ontology_data["entities"].items():
            if name == "ExtractedRelationship":
                continue
            desc = entity.get("description", "")
            assert "ArchiMate" in desc or "archimate" in desc.lower(), (
                f"Entity '{name}' description should reference ArchiMate standard"
            )


class TestRelationshipDefinitions:
    """Validate relationship metadata in ontology.yaml."""

    def test_each_relationship_has_description(self, ontology_data):
        for name, rel in ontology_data["relationships"].items():
            assert "description" in rel, f"Relationship '{name}' missing description"

    def test_each_relationship_has_category(self, ontology_data):
        valid_categories = {"Structural", "Dependency", "Dynamic", "Other"}
        for name, rel in ontology_data["relationships"].items():
            cat = rel.get("category")
            assert cat in valid_categories, (
                f"Relationship '{name}' has invalid category '{cat}'. "
                f"Must be one of {valid_categories}"
            )

    def test_structural_relationships_correct(self, ontology_data):
        structural = {
            name for name, r in ontology_data["relationships"].items()
            if r.get("category") == "Structural"
        }
        expected = {"Composition", "Aggregation", "Assignment", "Realization"}
        assert structural == expected, f"Structural relationships mismatch: {structural} vs {expected}"

    def test_dependency_relationships_correct(self, ontology_data):
        dependency = {
            name for name, r in ontology_data["relationships"].items()
            if r.get("category") == "Dependency"
        }
        expected = {"Serving", "Access", "Influence", "Association"}
        assert dependency == expected

    def test_dynamic_relationships_correct(self, ontology_data):
        dynamic = {
            name for name, r in ontology_data["relationships"].items()
            if r.get("category") == "Dynamic"
        }
        expected = {"Triggering", "Flow"}
        assert dynamic == expected


class TestExtractedEntitiesRoot:
    """Validate the root extraction object maps all entity types."""

    def test_extracted_entities_has_all_lists(self, ontology_data):
        """The root extraction model should have a list field for each entity type."""
        ee = ontology_data.get("extracted_entities", {})
        fields = set(ee.get("fields", {}).keys())
        # At minimum, should have one list per entity type
        assert len(fields) >= 22, (
            f"extracted_entities has only {len(fields)} fields, expected >= 22"
        )


class TestDynamicPydanticModels:
    """Validate that ontology.py can dynamically generate Pydantic models."""

    def test_dynamic_loading_succeeds(self):
        from models.ontology import ExtractedEntities, DynamicEntities
        assert ExtractedEntities is not None
        assert DynamicEntities is not None

    def test_all_entity_models_generated(self):
        from models.ontology import DynamicEntities
        for entity_type in ARCHIMATE_ENTITY_TYPES:
            assert entity_type in DynamicEntities, (
                f"Pydantic model not generated for '{entity_type}'"
            )

    def test_entity_model_has_correct_fields(self):
        from models.ontology import DynamicEntities
        for entity_type in ARCHIMATE_ENTITY_TYPES:
            model = DynamicEntities[entity_type]
            field_names = set(model.model_fields.keys())
            assert "description" in field_names, (
                f"Model '{entity_type}' missing 'description' field"
            )
            assert "archimate_layer" in field_names, (
                f"Model '{entity_type}' missing 'archimate_layer' field"
            )

    def test_extracted_entities_model_instantiates(self):
        from models.ontology import ExtractedEntities
        # Should instantiate with all-empty lists
        instance = ExtractedEntities()
        assert instance is not None

    def test_entity_model_validates_correctly(self):
        """Test that a sample entity validates through Pydantic."""
        from models.ontology import DynamicEntities
        AppComp = DynamicEntities["ApplicationComponent"]
        instance = AppComp(
            app_id="test-001",
            app_name="Test CRM",
            description="A test CRM system",
            archimate_layer="Application",
            source_doc_id="doc-001",
        )
        assert instance.app_name == "Test CRM"
        assert instance.archimate_layer == "Application"
