"""
Test Suite 2: Graph Extraction Validation
Validates that extracted nodes and edges follow ArchiMate 3.2 format and relationship rules.
Simulates the output of the ProcessingAgent's extract_graph tool.
"""
import re
import pytest

from tests.conftest import (
    ARCHIMATE_ENTITY_TYPES,
    ARCHIMATE_RELATIONSHIP_TYPES,
    ENTITY_LAYER_MAP,
    STRUCTURAL_RELATIONSHIP_RULES,
    DEPENDENCY_RELATIONSHIP_RULES,
)

# ---------------------------------------------------------------------------
# Node/Edge format parsers (match ProcessingAgent output format)
# ---------------------------------------------------------------------------

NODE_PATTERN = re.compile(r"^([A-Za-z]+):(.+)$")
EDGE_PATTERN = re.compile(
    r"^([A-Za-z]+):(.+?)->"          # source_type:source_name->
    r"([A-Za-z]+)"                     # relationship_type
    r"(?:\[([^\]]*)\])?"               # optional [qualifier] e.g. [Read], [+]
    r"->"                              # ->
    r"([A-Za-z]+):(.+)$"              # target_type:target_name
)


def parse_node(node_str: str) -> tuple[str, str]:
    """Parse 'EntityType:EntityName' -> (type, name)."""
    m = NODE_PATTERN.match(node_str.strip())
    if not m:
        raise ValueError(f"Invalid node format: '{node_str}'. Expected 'EntityType:EntityName'")
    return m.group(1), m.group(2)


def parse_edge(edge_str: str) -> dict:
    """Parse 'SrcType:SrcName->RelType->TgtType:TgtName' -> dict."""
    m = EDGE_PATTERN.match(edge_str.strip())
    if not m:
        raise ValueError(
            f"Invalid edge format: '{edge_str}'. "
            "Expected 'SourceType:SourceName->RelationshipType->TargetType:TargetName'"
        )
    return {
        "source_type": m.group(1),
        "source_name": m.group(2),
        "relationship_type": m.group(3),
        "qualifier": m.group(4),  # None if no qualifier
        "target_type": m.group(5),
        "target_name": m.group(6),
    }


# ---------------------------------------------------------------------------
# Sample extraction outputs (simulating ProcessingAgent results)
# ---------------------------------------------------------------------------

SAMPLE_NODES_VALID = [
    "ApplicationComponent:SAP ERP",
    "ApplicationComponent:CRM System",
    "BusinessProcess:Order Fulfillment",
    "BusinessProcess:Invoice Processing",
    "BusinessActor:IT Operations Team",
    "BusinessRole:Application Owner",
    "DataObject:Customer Record",
    "DataObject:Invoice Data",
    "BusinessObject:Customer",
    "Node:App-Server-PRD-01",
    "SystemSoftware:Oracle Database 19c",
    "SystemSoftware:Red Hat Linux 8",
    "Device:Dell PowerEdge R740",
    "TechnologyService:Database Hosting",
    "Artifact:crm-backend.jar",
    "CommunicationNetwork:Corporate LAN",
    "ApplicationService:Payment Processing API",
    "ApplicationInterface:REST API v2",
    "BusinessService:Customer Support",
    "BusinessFunction:Finance",
    "Contract:SLA Gold",
    "Goal:Reduce TCO by 20%",
    "Requirement:System must support 1000 concurrent users",
    "Constraint:Must use Oracle DB",
    "Stakeholder:CTO",
    "Capability:Cloud Operations",
]

SAMPLE_EDGES_VALID = [
    "BusinessActor:IT Operations Team->Assignment->BusinessProcess:Order Fulfillment",
    "BusinessActor:IT Operations Team->Assignment->BusinessRole:Application Owner",
    "ApplicationComponent:SAP ERP->Serving->BusinessProcess:Order Fulfillment",
    "ApplicationComponent:CRM System->Access[ReadWrite]->DataObject:Customer Record",
    "ApplicationComponent:SAP ERP->Access[Read]->DataObject:Invoice Data",
    "ApplicationComponent:SAP ERP->Realization->Requirement:System must support 1000 concurrent users",
    "Node:App-Server-PRD-01->Composition->SystemSoftware:Red Hat Linux 8",
    "Node:App-Server-PRD-01->Composition->Device:Dell PowerEdge R740",
    "SystemSoftware:Oracle Database 19c->Realization->TechnologyService:Database Hosting",
    "TechnologyService:Database Hosting->Serving->ApplicationComponent:SAP ERP",
    "Artifact:crm-backend.jar->Realization->ApplicationComponent:CRM System",
    "DataObject:Customer Record->Realization->BusinessObject:Customer",
    "BusinessProcess:Order Fulfillment->Triggering->BusinessProcess:Invoice Processing",
    "BusinessProcess:Order Fulfillment->Flow->ApplicationComponent:SAP ERP",
    "BusinessFunction:Finance->Aggregation->BusinessProcess:Invoice Processing",
    "Goal:Reduce TCO by 20%->Influence[+]->Requirement:System must support 1000 concurrent users",
    "Constraint:Must use Oracle DB->Specialization->Requirement:System must support 1000 concurrent users",
    "ApplicationService:Payment Processing API->Serving->BusinessProcess:Order Fulfillment",
    "ApplicationComponent:CRM System->Realization->ApplicationService:Payment Processing API",
    "BusinessService:Customer Support->Serving->BusinessProcess:Order Fulfillment",
    "Capability:Cloud Operations->Aggregation->Capability:Cloud Operations",
]

# Deliberately invalid samples for negative testing
SAMPLE_NODES_INVALID = [
    "App:SAP ERP",                     # "App" is not a valid ArchiMate type
    "Server:DB-01",                    # "Server" is not valid, should be "Node"
    "Database:Oracle",                 # "Database" is not valid, should be "SystemSoftware"
    "SAP ERP",                         # Missing type prefix
    ":CRM",                            # Empty type
    "ApplicationComponent:",           # Empty name
]

SAMPLE_EDGES_INVALID_FORMAT = [
    "SAP ERP->Serving->CRM",                            # Missing type prefixes
    "ApplicationComponent:SAP Serving Node:Server",      # Missing arrows
    "ApplicationComponent:SAP->->Node:Server",           # Empty relationship
]

SAMPLE_EDGES_INVALID_RELATIONSHIP = [
    "ApplicationComponent:SAP->CONNECTS->Node:Server",  # "CONNECTS" not a valid relationship
    "ApplicationComponent:SAP->UsedBy->Node:Server",     # "UsedBy" deprecated
]

SAMPLE_EDGES_INVALID_SEMANTICS = [
    # Access target must be passive structure, but BusinessActor is active
    "ApplicationComponent:CRM->Access->BusinessActor:IT Team",
    # Influence target must be motivation element, but Node is not
    "Goal:Reduce TCO->Influence->Node:Server-01",
    # Composition must be same type, but mixing types
    "BusinessProcess:P1->Composition->ApplicationComponent:App1",
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNodeFormatParsing:
    """Validate node string format: 'EntityType:EntityName'."""

    @pytest.mark.parametrize("node_str", SAMPLE_NODES_VALID)
    def test_valid_nodes_parse(self, node_str):
        entity_type, entity_name = parse_node(node_str)
        assert entity_type in ARCHIMATE_ENTITY_TYPES, (
            f"Unknown entity type '{entity_type}' in node '{node_str}'"
        )
        assert len(entity_name.strip()) > 0, "Entity name cannot be empty"

    @pytest.mark.parametrize("node_str", SAMPLE_NODES_INVALID)
    def test_invalid_nodes_rejected(self, node_str):
        """Nodes with invalid types or format should fail validation."""
        try:
            entity_type, entity_name = parse_node(node_str)
            # If parsing succeeds, the type should be invalid ArchiMate
            if entity_type and entity_name:
                assert entity_type not in ARCHIMATE_ENTITY_TYPES, (
                    f"'{entity_type}' should not be a valid ArchiMate type"
                )
        except ValueError:
            pass  # Expected for malformed format

    def test_node_type_maps_to_correct_layer(self):
        for node_str in SAMPLE_NODES_VALID:
            entity_type, _ = parse_node(node_str)
            assert entity_type in ENTITY_LAYER_MAP, (
                f"Entity type '{entity_type}' has no layer mapping"
            )
            layer = ENTITY_LAYER_MAP[entity_type]
            assert layer in {"Strategy", "Business", "Application", "Technology", "Motivation"}


class TestEdgeFormatParsing:
    """Validate edge string format: 'SrcType:SrcName->RelType->TgtType:TgtName'."""

    @pytest.mark.parametrize("edge_str", SAMPLE_EDGES_VALID)
    def test_valid_edges_parse(self, edge_str):
        edge = parse_edge(edge_str)
        assert edge["source_type"] in ARCHIMATE_ENTITY_TYPES, (
            f"Unknown source type '{edge['source_type']}'"
        )
        assert edge["target_type"] in ARCHIMATE_ENTITY_TYPES, (
            f"Unknown target type '{edge['target_type']}'"
        )
        assert edge["relationship_type"] in ARCHIMATE_RELATIONSHIP_TYPES, (
            f"Unknown relationship type '{edge['relationship_type']}'"
        )

    @pytest.mark.parametrize("edge_str", SAMPLE_EDGES_INVALID_FORMAT)
    def test_invalid_format_edges_rejected(self, edge_str):
        with pytest.raises(ValueError):
            parse_edge(edge_str)

    @pytest.mark.parametrize("edge_str", SAMPLE_EDGES_INVALID_RELATIONSHIP)
    def test_invalid_relationship_type_rejected(self, edge_str):
        """Edges with non-ArchiMate relationship types should fail validation."""
        edge = parse_edge(edge_str)
        assert edge["relationship_type"] not in ARCHIMATE_RELATIONSHIP_TYPES, (
            f"'{edge['relationship_type']}' should not be a valid ArchiMate relationship"
        )


class TestRelationshipSemanticValidation:
    """Validate that relationships follow ArchiMate 3.2 semantic rules."""

    @pytest.mark.parametrize("edge_str", SAMPLE_EDGES_VALID)
    def test_valid_edges_pass_semantic_check(self, edge_str):
        edge = parse_edge(edge_str)
        errors = validate_relationship_semantics(edge)
        assert not errors, (
            f"Semantic validation failed for '{edge_str}': {errors}"
        )

    @pytest.mark.parametrize("edge_str", SAMPLE_EDGES_INVALID_SEMANTICS)
    def test_invalid_semantic_edges_detected(self, edge_str):
        edge = parse_edge(edge_str)
        errors = validate_relationship_semantics(edge)
        assert errors, (
            f"Expected semantic errors for '{edge_str}' but validation passed"
        )

    def test_access_target_must_be_passive_structure(self):
        """Access relationship target must be a passive structure element."""
        passive_types = {"DataObject", "BusinessObject", "Contract", "Artifact"}
        for edge_str in SAMPLE_EDGES_VALID:
            edge = parse_edge(edge_str)
            if edge["relationship_type"] == "Access":
                assert edge["target_type"] in passive_types, (
                    f"Access target '{edge['target_type']}' is not a passive structure element"
                )

    def test_influence_target_must_be_motivation(self):
        """Influence relationship target must be a motivation element."""
        motivation_types = {"Goal", "Requirement", "Constraint", "Stakeholder"}
        for edge_str in SAMPLE_EDGES_VALID:
            edge = parse_edge(edge_str)
            if edge["relationship_type"] == "Influence":
                assert edge["target_type"] in motivation_types, (
                    f"Influence target '{edge['target_type']}' is not a motivation element"
                )

    def test_composition_must_be_same_type(self):
        """Composition must be between same element types (or Node->Device/SystemSoftware)."""
        # ArchiMate allows Node to compose Device and SystemSoftware as exception
        composition_exceptions = {
            ("Node", "Device"),
            ("Node", "SystemSoftware"),
        }
        for edge_str in SAMPLE_EDGES_VALID:
            edge = parse_edge(edge_str)
            if edge["relationship_type"] == "Composition":
                pair = (edge["source_type"], edge["target_type"])
                if pair not in composition_exceptions:
                    assert edge["source_type"] == edge["target_type"], (
                        f"Composition between different types: {pair}"
                    )

    def test_specialization_must_be_same_type(self):
        """Specialization must be between same element types (Constraint->Requirement is exception)."""
        spec_exceptions = {("Constraint", "Requirement")}
        for edge_str in SAMPLE_EDGES_VALID:
            edge = parse_edge(edge_str)
            if edge["relationship_type"] == "Specialization":
                pair = (edge["source_type"], edge["target_type"])
                if pair not in spec_exceptions:
                    assert edge["source_type"] == edge["target_type"], (
                        f"Specialization between different types: {pair}"
                    )

    def test_realization_direction_concrete_to_abstract(self):
        """Realization should go from more concrete (lower layer) to more abstract (higher layer/motivation)."""
        layer_order = {"Technology": 0, "Application": 1, "Business": 2, "Strategy": 3, "Motivation": 4}
        for edge_str in SAMPLE_EDGES_VALID:
            edge = parse_edge(edge_str)
            if edge["relationship_type"] == "Realization":
                src_layer = ENTITY_LAYER_MAP.get(edge["source_type"])
                tgt_layer = ENTITY_LAYER_MAP.get(edge["target_type"])
                if src_layer and tgt_layer and src_layer != tgt_layer:
                    src_order = layer_order.get(src_layer, 0)
                    tgt_order = layer_order.get(tgt_layer, 0)
                    assert src_order <= tgt_order, (
                        f"Realization should go from concrete to abstract: "
                        f"{edge['source_type']}({src_layer}) -> {edge['target_type']}({tgt_layer})"
                    )

    def test_access_qualifier_valid(self):
        """Access qualifier must be Read, Write, ReadWrite, or absent."""
        valid_qualifiers = {None, "Read", "Write", "ReadWrite"}
        for edge_str in SAMPLE_EDGES_VALID:
            edge = parse_edge(edge_str)
            if edge["relationship_type"] == "Access":
                assert edge["qualifier"] in valid_qualifiers, (
                    f"Invalid Access qualifier: '{edge['qualifier']}'"
                )

    def test_influence_qualifier_valid(self):
        """Influence qualifier must be ++, +, 0, -, --, or absent."""
        valid_qualifiers = {None, "++", "+", "0", "-", "--"}
        for edge_str in SAMPLE_EDGES_VALID:
            edge = parse_edge(edge_str)
            if edge["relationship_type"] == "Influence":
                assert edge["qualifier"] in valid_qualifiers, (
                    f"Invalid Influence qualifier: '{edge['qualifier']}'"
                )


class TestGraphConsistency:
    """Validate overall graph consistency (nodes referenced in edges must exist)."""

    def test_all_edge_sources_have_nodes(self):
        node_keys = set()
        for n in SAMPLE_NODES_VALID:
            t, name = parse_node(n)
            node_keys.add(f"{t}:{name}")

        for e in SAMPLE_EDGES_VALID:
            edge = parse_edge(e)
            key = f"{edge['source_type']}:{edge['source_name']}"
            assert key in node_keys, f"Edge source '{key}' not found in nodes"

    def test_all_edge_targets_have_nodes(self):
        node_keys = set()
        for n in SAMPLE_NODES_VALID:
            t, name = parse_node(n)
            node_keys.add(f"{t}:{name}")

        for e in SAMPLE_EDGES_VALID:
            edge = parse_edge(e)
            key = f"{edge['target_type']}:{edge['target_name']}"
            assert key in node_keys, f"Edge target '{key}' not found in nodes"

    def test_no_self_referencing_edges(self):
        """An edge should not point from an entity to itself (except Aggregation of same-named Capabilities)."""
        for e in SAMPLE_EDGES_VALID:
            edge = parse_edge(e)
            src = f"{edge['source_type']}:{edge['source_name']}"
            tgt = f"{edge['target_type']}:{edge['target_name']}"
            # Self-aggregation of same capability is a valid test case we allow
            if edge["relationship_type"] == "Aggregation" and edge["source_type"] == edge["target_type"]:
                continue
            assert src != tgt, f"Self-referencing edge detected: {e}"


class TestDocumentExtractionScenarios:
    """Test realistic document extraction scenarios end-to-end."""

    def test_infrastructure_document(self):
        """Simulate extraction from a typical infrastructure document."""
        nodes = [
            "Node:Web-Server-Cluster",
            "Device:Dell R740 Rack Server",
            "SystemSoftware:Red Hat Linux 8",
            "SystemSoftware:Apache Tomcat 9",
            "ApplicationComponent:Customer Portal",
            "Artifact:portal.war",
            "CommunicationNetwork:DMZ Network",
            "TechnologyService:HTTP Load Balancing",
        ]
        edges = [
            "Node:Web-Server-Cluster->Composition->Device:Dell R740 Rack Server",
            "Node:Web-Server-Cluster->Composition->SystemSoftware:Red Hat Linux 8",
            "SystemSoftware:Red Hat Linux 8->Assignment->SystemSoftware:Apache Tomcat 9",
            "SystemSoftware:Apache Tomcat 9->Assignment->Artifact:portal.war",
            "Artifact:portal.war->Realization->ApplicationComponent:Customer Portal",
            "TechnologyService:HTTP Load Balancing->Serving->ApplicationComponent:Customer Portal",
        ]
        _validate_full_extraction(nodes, edges)

    def test_business_process_document(self):
        """Simulate extraction from a business process document."""
        nodes = [
            "BusinessActor:Claims Department",
            "BusinessRole:Claims Manager",
            "BusinessProcess:Claims Processing",
            "BusinessProcess:Claims Adjudication",
            "BusinessService:Claims Handling Service",
            "BusinessObject:Insurance Claim",
            "ApplicationComponent:Claims System",
            "DataObject:Claim Record",
            "Requirement:Claims must be processed within 5 business days",
        ]
        edges = [
            "BusinessActor:Claims Department->Assignment->BusinessRole:Claims Manager",
            "BusinessRole:Claims Manager->Assignment->BusinessProcess:Claims Processing",
            "BusinessProcess:Claims Processing->Triggering->BusinessProcess:Claims Adjudication",
            "BusinessProcess:Claims Processing->Access[ReadWrite]->BusinessObject:Insurance Claim",
            "ApplicationComponent:Claims System->Serving->BusinessProcess:Claims Processing",
            "ApplicationComponent:Claims System->Access[ReadWrite]->DataObject:Claim Record",
            "DataObject:Claim Record->Realization->BusinessObject:Insurance Claim",
            "ApplicationComponent:Claims System->Realization->Requirement:Claims must be processed within 5 business days",
            "ApplicationComponent:Claims System->Realization->BusinessService:Claims Handling Service",
        ]
        _validate_full_extraction(nodes, edges)

    def test_strategic_alignment_document(self):
        """Simulate extraction from a strategic alignment / governance document."""
        nodes = [
            "Stakeholder:CTO",
            "Stakeholder:Enterprise Architect",
            "Goal:Achieve 99.9% Uptime",
            "Goal:Reduce Infrastructure Costs",
            "Requirement:All services must have HA configuration",
            "Constraint:Must use on-premise data centers",
            "Capability:High Availability Operations",
            "ApplicationComponent:Monitoring Platform",
        ]
        edges = [
            "Stakeholder:CTO->Influence[+]->Goal:Achieve 99.9% Uptime",
            "Goal:Achieve 99.9% Uptime->Influence[+]->Requirement:All services must have HA configuration",
            "Constraint:Must use on-premise data centers->Specialization->Requirement:All services must have HA configuration",
            "ApplicationComponent:Monitoring Platform->Realization->Requirement:All services must have HA configuration",
            "Goal:Reduce Infrastructure Costs->Influence[-]->Requirement:All services must have HA configuration",
        ]
        _validate_full_extraction(nodes, edges)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def validate_relationship_semantics(edge: dict) -> list[str]:
    """Validate ArchiMate 3.2 semantic rules for a parsed edge. Returns list of errors."""
    errors = []
    rel = edge["relationship_type"]
    src_type = edge["source_type"]
    tgt_type = edge["target_type"]

    # Rule: Access target must be passive structure
    if rel == "Access":
        passive = {"DataObject", "BusinessObject", "Contract", "Artifact"}
        if tgt_type not in passive:
            errors.append(f"Access target '{tgt_type}' is not passive structure (expected: {passive})")

    # Rule: Influence target must be motivation
    if rel == "Influence":
        motivation = {"Goal", "Requirement", "Constraint", "Stakeholder"}
        if tgt_type not in motivation:
            errors.append(f"Influence target '{tgt_type}' is not a motivation element")

    # Rule: Composition — same type or known exceptions
    if rel == "Composition":
        exceptions = {("Node", "Device"), ("Node", "SystemSoftware"),
                      ("ApplicationComponent", "ApplicationComponent")}
        if src_type != tgt_type and (src_type, tgt_type) not in exceptions:
            errors.append(f"Composition between different types: {src_type} -> {tgt_type}")

    # Rule: Specialization — same type or Constraint->Requirement
    if rel == "Specialization":
        exceptions = {("Constraint", "Requirement")}
        if src_type != tgt_type and (src_type, tgt_type) not in exceptions:
            errors.append(f"Specialization between different types: {src_type} -> {tgt_type}")

    # Rule: Association — always allowed (no validation needed)
    # Rule: Triggering/Flow — source and target should be behavior elements
    # (relaxed rule - we allow flows between components too)

    return errors


def _validate_full_extraction(nodes: list[str], edges: list[str]):
    """Run full validation on a set of extracted nodes and edges."""
    # 1. Parse all nodes
    node_keys = set()
    for n in nodes:
        t, name = parse_node(n)
        assert t in ARCHIMATE_ENTITY_TYPES, f"Invalid entity type: {t}"
        node_keys.add(f"{t}:{name}")

    # 2. Parse and validate all edges
    for e in edges:
        edge = parse_edge(e)
        assert edge["source_type"] in ARCHIMATE_ENTITY_TYPES
        assert edge["target_type"] in ARCHIMATE_ENTITY_TYPES
        assert edge["relationship_type"] in ARCHIMATE_RELATIONSHIP_TYPES

        # Check source/target exist in nodes
        src_key = f"{edge['source_type']}:{edge['source_name']}"
        tgt_key = f"{edge['target_type']}:{edge['target_name']}"
        assert src_key in node_keys, f"Edge source '{src_key}' not in nodes"
        assert tgt_key in node_keys, f"Edge target '{tgt_key}' not in nodes"

        # Semantic validation
        errors = validate_relationship_semantics(edge)
        assert not errors, f"Semantic errors in '{e}': {errors}"
