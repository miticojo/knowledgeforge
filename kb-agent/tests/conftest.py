"""Shared fixtures for ArchiMate 3.2 E2E tests."""
import os
import sys
import pytest
import yaml

# Ensure the agent package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# ArchiMate 3.2 Wave 2 — canonical sets loaded once
# ---------------------------------------------------------------------------

ARCHIMATE_ENTITY_TYPES = frozenset({
    # Strategy
    "Capability",
    # Business
    "BusinessActor", "BusinessRole", "BusinessProcess", "BusinessFunction",
    "BusinessService", "BusinessObject", "Contract",
    # Application
    "ApplicationComponent", "ApplicationService", "ApplicationInterface", "DataObject",
    # Technology
    "Node", "Device", "SystemSoftware", "TechnologyService", "Artifact",
    "CommunicationNetwork",
    # Motivation
    "Goal", "Requirement", "Constraint", "Stakeholder",
})

ARCHIMATE_RELATIONSHIP_TYPES = frozenset({
    "Composition", "Aggregation", "Assignment", "Realization",
    "Serving", "Access", "Influence", "Association",
    "Triggering", "Flow", "Specialization",
})

ARCHIMATE_LAYERS = frozenset({
    "Strategy", "Business", "Application", "Technology", "Motivation",
})

# Map each entity to its expected layer
ENTITY_LAYER_MAP = {
    "Capability": "Strategy",
    "BusinessActor": "Business", "BusinessRole": "Business",
    "BusinessProcess": "Business", "BusinessFunction": "Business",
    "BusinessService": "Business", "BusinessObject": "Business",
    "Contract": "Business",
    "ApplicationComponent": "Application", "ApplicationService": "Application",
    "ApplicationInterface": "Application", "DataObject": "Application",
    "Node": "Technology", "Device": "Technology",
    "SystemSoftware": "Technology", "TechnologyService": "Technology",
    "Artifact": "Technology", "CommunicationNetwork": "Technology",
    "Goal": "Motivation", "Requirement": "Motivation",
    "Constraint": "Motivation", "Stakeholder": "Motivation",
}

# --- Relationship direction rules (ArchiMate 3.2 normative) ---
# For each relationship type, define which (source_aspect, target_aspect) combos are valid.
# aspect = Active Structure | Behavior | Passive Structure | Motivation | Strategy | Composite

STRUCTURAL_RELATIONSHIP_RULES = {
    "Composition": {
        "rule": "same_type_only",
        "description": "Source and target must be the same element type",
    },
    "Aggregation": {
        "rule": "same_type_only",
        "description": "Source and target must be the same element type",
    },
    "Assignment": {
        "valid_patterns": [
            # Active Structure -> Behavior
            ({"BusinessActor", "BusinessRole"}, {"BusinessProcess", "BusinessFunction", "BusinessService"}),
            ({"BusinessActor", "BusinessRole"}, {"ApplicationComponent"}),
            # Technology assignment
            ({"Node", "Device", "SystemSoftware"}, {"Artifact", "ApplicationComponent", "SystemSoftware", "TechnologyService"}),
            # Actor -> Role
            ({"BusinessActor"}, {"BusinessRole"}),
        ],
    },
    "Realization": {
        "valid_patterns": [
            # App -> Business
            ({"ApplicationComponent", "ApplicationService"}, {"BusinessProcess", "BusinessService", "BusinessFunction", "Requirement"}),
            # Technology -> TechService
            ({"Node", "SystemSoftware", "Device"}, {"TechnologyService"}),
            # Artifact -> App/Data
            ({"Artifact"}, {"ApplicationComponent", "DataObject"}),
            # Data -> Business object
            ({"DataObject"}, {"BusinessObject"}),
            # Any core -> Motivation
            (ARCHIMATE_ENTITY_TYPES - {"Goal", "Requirement", "Constraint", "Stakeholder"},
             {"Goal", "Requirement", "Constraint"}),
        ],
    },
}

DEPENDENCY_RELATIONSHIP_RULES = {
    "Serving": {
        "valid_patterns": [
            ({"ApplicationComponent", "ApplicationService"}, {"BusinessProcess", "BusinessFunction", "BusinessService", "ApplicationComponent"}),
            ({"TechnologyService", "SystemSoftware", "Node"}, {"ApplicationComponent", "Node", "SystemSoftware"}),
            ({"BusinessService"}, {"BusinessProcess", "BusinessFunction", "BusinessActor", "BusinessRole"}),
        ],
    },
    "Access": {
        "target_restriction": {"DataObject", "BusinessObject", "Contract", "Artifact"},
        "description": "Target must be a passive structure element",
    },
    "Influence": {
        "target_restriction": {"Goal", "Requirement", "Constraint", "Stakeholder"},
        "description": "Target must be a motivation element",
    },
    "Association": {
        "rule": "any_to_any",
    },
}


# --- Valid Spanner GQL patterns ---

SPANNER_GQL_KEYWORDS = {
    "GRAPH", "MATCH", "RETURN", "WHERE", "LET", "WITH", "FILTER",
    "ORDER", "BY", "LIMIT", "OFFSET", "SKIP", "NEXT",
    "GROUP", "OPTIONAL", "CALL", "FOR", "IN",
    "UNION", "ALL", "INTERSECT", "EXCEPT",
    "ASC", "DESC", "AS", "NOT", "AND", "OR",
    "IS", "NULL", "TRUE", "FALSE", "COUNT", "SUM", "AVG", "MIN", "MAX",
}


@pytest.fixture
def ontology_data():
    """Load the current ontology.yaml."""
    yaml_path = os.path.join(os.path.dirname(__file__), "..", "ontology.yaml")
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def spanner_ddl():
    """Load the Spanner schema DDL as raw text."""
    ddl_path = os.path.join(os.path.dirname(__file__), "..", "..", "database", "spanner_schema.sdl")
    with open(ddl_path, "r", encoding="utf-8") as f:
        return f.read()
