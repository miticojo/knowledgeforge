"""
Test Suite 3: Spanner Graph GQL Syntax Validation
Validates that generated GQL queries follow Cloud Spanner Graph Query Language syntax.
Reference: https://cloud.google.com/spanner/docs/reference/standard-sql/graph-query-statements
"""
import re
import pytest

from tests.conftest import (
    ARCHIMATE_ENTITY_TYPES,
    ARCHIMATE_RELATIONSHIP_TYPES,
    ENTITY_LAYER_MAP,
)

# ---------------------------------------------------------------------------
# The Knowledge Graph name (from spanner_schema.sdl)
# ---------------------------------------------------------------------------
GRAPH_NAME = "KnowledgeGraph"

# Node labels = Spanner table names (plural)
NODE_LABELS = {
    # Existing Wave 1
    "ApplicationComponents", "DataObjects", "BusinessProcesses", "Requirements",
    "Nodes", "SystemSoftwares", "TechnologyServices", "BusinessActors", "Documents",
    # Wave 2 additions
    "BusinessRoles", "BusinessServices", "BusinessFunctions", "BusinessObjects",
    "ApplicationServices", "ApplicationInterfaces", "Artifacts", "Devices",
    "CommunicationNetworks", "Contracts", "Goals", "Constraints", "Stakeholders",
    "Capabilities",
}

# Edge labels = relationship type names (from Property Graph LABEL)
EDGE_LABELS = {
    "Composition", "Aggregation", "Assignment", "Realization",
    "Serving", "Access", "Influence", "Association",
    "Triggering", "Flow", "Specialization",
    "Mentions",  # DocumentMentions edge
}

# Map entity type -> table name (label in GQL)
ENTITY_TO_LABEL = {
    "ApplicationComponent": "ApplicationComponents",
    "DataObject": "DataObjects",
    "BusinessProcess": "BusinessProcesses",
    "Requirement": "Requirements",
    "Node": "Nodes",
    "SystemSoftware": "SystemSoftwares",
    "TechnologyService": "TechnologyServices",
    "BusinessActor": "BusinessActors",
    "BusinessRole": "BusinessRoles",
    "BusinessService": "BusinessServices",
    "BusinessFunction": "BusinessFunctions",
    "BusinessObject": "BusinessObjects",
    "ApplicationService": "ApplicationServices",
    "ApplicationInterface": "ApplicationInterfaces",
    "Artifact": "Artifacts",
    "Device": "Devices",
    "CommunicationNetwork": "CommunicationNetworks",
    "Contract": "Contracts",
    "Goal": "Goals",
    "Constraint": "Constraints",
    "Stakeholder": "Stakeholders",
    "Capability": "Capabilities",
}


# ---------------------------------------------------------------------------
# GQL Query Generator (mirrors what the search agent should produce)
# ---------------------------------------------------------------------------

def generate_find_entity_query(entity_type: str, name_filter: str | None = None) -> str:
    """Generate GQL to find entities by type (and optionally by name)."""
    label = ENTITY_TO_LABEL[entity_type]
    if name_filter:
        return (
            f"GRAPH {GRAPH_NAME}\n"
            f"  MATCH (n:{label})\n"
            f"  WHERE n.{_name_field(entity_type)} = '{name_filter}'\n"
            f"  RETURN n"
        )
    return (
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (n:{label})\n"
        f"  RETURN n"
    )


def generate_find_related_query(
    entity_type: str, entity_name: str, relationship: str, direction: str = "outgoing"
) -> str:
    """Generate GQL to find entities related via a specific relationship."""
    label = ENTITY_TO_LABEL[entity_type]
    name_field = _name_field(entity_type)
    if direction == "outgoing":
        return (
            f"GRAPH {GRAPH_NAME}\n"
            f"  MATCH (src:{label})-[e:{relationship}]->(tgt)\n"
            f"  WHERE src.{name_field} = '{entity_name}'\n"
            f"  RETURN src, e, tgt"
        )
    elif direction == "incoming":
        return (
            f"GRAPH {GRAPH_NAME}\n"
            f"  MATCH (src)-[e:{relationship}]->(tgt:{label})\n"
            f"  WHERE tgt.{name_field} = '{entity_name}'\n"
            f"  RETURN src, e, tgt"
        )
    else:  # any direction
        return (
            f"GRAPH {GRAPH_NAME}\n"
            f"  MATCH (src:{label})-[e:{relationship}]-(tgt)\n"
            f"  WHERE src.{name_field} = '{entity_name}'\n"
            f"  RETURN src, e, tgt"
        )


def generate_multi_hop_query(
    start_type: str, start_name: str,
    hops: list[tuple[str, str]],  # [(relationship, target_type), ...]
) -> str:
    """Generate GQL for multi-hop traversal."""
    start_label = ENTITY_TO_LABEL[start_type]
    name_field = _name_field(start_type)

    path_parts = [f"(n0:{start_label})"]
    for i, (rel, tgt_type) in enumerate(hops):
        tgt_label = ENTITY_TO_LABEL[tgt_type]
        path_parts.append(f"-[e{i}:{rel}]->(n{i+1}:{tgt_label})")

    match_pattern = "".join(path_parts)
    return_vars = ", ".join([f"n{i}" for i in range(len(hops) + 1)])

    return (
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH {match_pattern}\n"
        f"  WHERE n0.{name_field} = '{start_name}'\n"
        f"  RETURN {return_vars}"
    )


def generate_aggregation_query(entity_type: str, group_by_field: str) -> str:
    """Generate GQL with GROUP BY and COUNT."""
    label = ENTITY_TO_LABEL[entity_type]
    return (
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (n:{label})-[e]->(tgt)\n"
        f"  RETURN n.{group_by_field} AS group_key, COUNT(tgt) AS count\n"
        f"  GROUP BY group_key\n"
        f"  ORDER BY count DESC"
    )


def generate_cross_layer_query(
    src_layer: str, tgt_layer: str, relationship: str
) -> str:
    """Generate GQL to find cross-layer relationships."""
    # Get all entity types in source and target layers
    src_types = [t for t, l in ENTITY_LAYER_MAP.items() if l == src_layer]
    tgt_types = [t for t, l in ENTITY_LAYER_MAP.items() if l == tgt_layer]

    # Use first type of each as representative
    src_label = ENTITY_TO_LABEL[src_types[0]]
    tgt_label = ENTITY_TO_LABEL[tgt_types[0]]

    return (
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (src:{src_label})-[e:{relationship}]->(tgt:{tgt_label})\n"
        f"  RETURN src, e, tgt"
    )


def generate_document_lineage_query(doc_title: str) -> str:
    """Generate GQL to find all entities mentioned in a document."""
    return (
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (doc:Documents)-[m:Mentions]->(entity)\n"
        f"  WHERE doc.title = '{doc_title}'\n"
        f"  RETURN doc.title AS document, entity, m.mention_context AS context"
    )


def generate_impact_analysis_query(entity_type: str, entity_name: str) -> str:
    """Generate GQL for impact analysis: find all entities reachable within 3 hops."""
    label = ENTITY_TO_LABEL[entity_type]
    name_field = _name_field(entity_type)
    return (
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (start:{label})-[e]->{{1,3}}(reachable)\n"
        f"  WHERE start.{name_field} = '{entity_name}'\n"
        f"  RETURN DISTINCT reachable"
    )


def generate_next_chained_query(entity_type: str, entity_name: str) -> str:
    """Generate GQL using NEXT to chain two linear queries."""
    label = ENTITY_TO_LABEL[entity_type]
    name_field = _name_field(entity_type)
    return (
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (src:{label})-[e:Serving]->(tgt)\n"
        f"  WHERE src.{name_field} = '{entity_name}'\n"
        f"  RETURN tgt, COUNT(e) AS serve_count\n"
        f"  GROUP BY tgt\n"
        f"  NEXT\n"
        f"  MATCH (tgt)-[e2:Access]->(data)\n"
        f"  RETURN tgt, data, serve_count"
    )


def _name_field(entity_type: str) -> str:
    """Return the canonical name field for an entity type."""
    field_map = {
        "ApplicationComponent": "app_name",
        "DataObject": "model_name",
        "BusinessProcess": "process_name",
        "Requirement": "title",
        "Node": "node_name",
        "SystemSoftware": "software_name",
        "TechnologyService": "service_name",
        "BusinessActor": "actor_name",
        "BusinessRole": "role_name",
        "BusinessService": "service_name",
        "BusinessFunction": "function_name",
        "BusinessObject": "object_name",
        "ApplicationService": "service_name",
        "ApplicationInterface": "interface_name",
        "Artifact": "artifact_name",
        "Device": "device_name",
        "CommunicationNetwork": "network_name",
        "Contract": "contract_name",
        "Goal": "goal_name",
        "Constraint": "constraint_name",
        "Stakeholder": "stakeholder_name",
        "Capability": "capability_name",
    }
    return field_map.get(entity_type, "name")


# ---------------------------------------------------------------------------
# GQL Syntax Validator
# ---------------------------------------------------------------------------

class GQLSyntaxValidator:
    """Lightweight syntax validator for Spanner Graph GQL statements."""

    # Basic structural checks
    GRAPH_CLAUSE = re.compile(r"GRAPH\s+\w+", re.IGNORECASE)
    MATCH_CLAUSE = re.compile(r"MATCH\s+", re.IGNORECASE)
    RETURN_CLAUSE = re.compile(r"RETURN\s+", re.IGNORECASE)

    # Node pattern: (var:Label) or (var:Label {prop: val}) or (var) or ()
    NODE_PATTERN = re.compile(r"\(\s*\w*\s*(?::\w+)?\s*(?:\{[^}]*\})?\s*\)")

    # Edge patterns: -[var:Label]-> or -[var:Label]- or <-[var:Label]-
    EDGE_FORWARD = re.compile(r"-\[[^\]]*\]->")
    EDGE_BACKWARD = re.compile(r"<-\[[^\]]*\]-")
    EDGE_UNDIRECTED = re.compile(r"-\[[^\]]*\]-(?!>)")
    EDGE_QUANTIFIED = re.compile(r"-\[[^\]]*\]->?\{[0-9]+,[0-9]+\}")

    # WHERE clause
    WHERE_CLAUSE = re.compile(r"WHERE\s+", re.IGNORECASE)

    # GROUP BY / ORDER BY
    GROUP_BY = re.compile(r"GROUP\s+BY\s+", re.IGNORECASE)
    ORDER_BY = re.compile(r"ORDER\s+BY\s+", re.IGNORECASE)

    # NEXT keyword
    NEXT_KEYWORD = re.compile(r"\bNEXT\b", re.IGNORECASE)

    def validate(self, query: str) -> list[str]:
        """Validate GQL syntax. Returns list of error messages (empty = valid)."""
        errors = []

        # Must start with GRAPH clause
        if not self.GRAPH_CLAUSE.search(query):
            errors.append("Missing GRAPH clause")

        # Must have at least one MATCH
        if not self.MATCH_CLAUSE.search(query):
            errors.append("Missing MATCH clause")

        # Must have at least one RETURN
        if not self.RETURN_CLAUSE.search(query):
            errors.append("Missing RETURN clause")

        # Must have at least one node pattern
        if not self.NODE_PATTERN.search(query):
            errors.append("No valid node pattern found")

        # Check balanced parentheses
        if query.count("(") != query.count(")"):
            errors.append("Unbalanced parentheses")

        # Check balanced brackets
        if query.count("[") != query.count("]"):
            errors.append("Unbalanced brackets")

        # Check balanced braces
        if query.count("{") != query.count("}"):
            errors.append("Unbalanced braces")

        # Node labels should be known
        for label_match in re.finditer(r"\(\w*:(\w+)", query):
            label = label_match.group(1)
            if label not in NODE_LABELS:
                errors.append(f"Unknown node label: '{label}'")

        # Edge labels should be known
        for label_match in re.finditer(r"\[\w*:(\w+)", query):
            label = label_match.group(1)
            if label not in EDGE_LABELS:
                errors.append(f"Unknown edge label: '{label}'")

        return errors


# Singleton validator
gql_validator = GQLSyntaxValidator()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGQLBasicSyntax:
    """Validate that generated GQL queries have correct syntax."""

    @pytest.mark.parametrize("entity_type", list(ENTITY_TO_LABEL.keys()))
    def test_find_entity_query_syntax(self, entity_type):
        query = generate_find_entity_query(entity_type)
        errors = gql_validator.validate(query)
        assert not errors, f"GQL syntax errors for {entity_type}: {errors}\nQuery:\n{query}"

    @pytest.mark.parametrize("entity_type", list(ENTITY_TO_LABEL.keys()))
    def test_find_entity_with_filter_syntax(self, entity_type):
        query = generate_find_entity_query(entity_type, "TestName")
        errors = gql_validator.validate(query)
        assert not errors, f"GQL syntax errors: {errors}\nQuery:\n{query}"

    @pytest.mark.parametrize("relationship", list(EDGE_LABELS - {"Mentions"}))
    def test_find_related_outgoing_syntax(self, relationship):
        query = generate_find_related_query(
            "ApplicationComponent", "SAP ERP", relationship, "outgoing"
        )
        errors = gql_validator.validate(query)
        assert not errors, f"GQL errors for {relationship}: {errors}\nQuery:\n{query}"

    @pytest.mark.parametrize("relationship", list(EDGE_LABELS - {"Mentions"}))
    def test_find_related_incoming_syntax(self, relationship):
        query = generate_find_related_query(
            "ApplicationComponent", "SAP ERP", relationship, "incoming"
        )
        errors = gql_validator.validate(query)
        assert not errors, f"GQL errors for {relationship}: {errors}\nQuery:\n{query}"


class TestGQLMultiHopQueries:
    """Validate multi-hop traversal GQL syntax."""

    def test_two_hop_app_to_business(self):
        query = generate_multi_hop_query(
            "ApplicationComponent", "SAP ERP",
            [("Serving", "BusinessProcess"), ("Access", "DataObject")]
        )
        errors = gql_validator.validate(query)
        assert not errors, f"GQL errors: {errors}\nQuery:\n{query}"

    def test_three_hop_tech_to_business(self):
        query = generate_multi_hop_query(
            "Node", "App-Server-01",
            [
                ("Assignment", "SystemSoftware"),
                ("Serving", "ApplicationComponent"),
                ("Serving", "BusinessProcess"),
            ]
        )
        errors = gql_validator.validate(query)
        assert not errors, f"GQL errors: {errors}\nQuery:\n{query}"

    def test_cross_layer_app_to_tech(self):
        query = generate_cross_layer_query("Application", "Technology", "Serving")
        errors = gql_validator.validate(query)
        assert not errors, f"GQL errors: {errors}\nQuery:\n{query}"


class TestGQLAggregationQueries:
    """Validate GQL with GROUP BY and aggregation functions."""

    def test_count_aggregation(self):
        query = generate_aggregation_query("ApplicationComponent", "app_name")
        errors = gql_validator.validate(query)
        assert not errors, f"GQL errors: {errors}\nQuery:\n{query}"
        assert "COUNT" in query
        assert "GROUP BY" in query

    def test_order_by_present(self):
        query = generate_aggregation_query("BusinessProcess", "process_name")
        assert "ORDER BY" in query


class TestGQLDocumentLineage:
    """Validate document lineage queries."""

    def test_document_mentions_query(self):
        query = generate_document_lineage_query("Architecture Overview v2")
        errors = gql_validator.validate(query)
        assert not errors, f"GQL errors: {errors}\nQuery:\n{query}"
        assert "Mentions" in query
        assert "Documents" in query


class TestGQLImpactAnalysis:
    """Validate variable-length path queries for impact analysis."""

    def test_impact_analysis_query_structure(self):
        query = generate_impact_analysis_query("ApplicationComponent", "CRM System")
        # Quantified path uses {min,max} syntax
        assert "{1,3}" in query
        assert "DISTINCT" in query
        # Basic structure checks
        assert "GRAPH" in query
        assert "MATCH" in query
        assert "RETURN" in query


class TestGQLNextChaining:
    """Validate NEXT-chained linear queries."""

    def test_next_chained_query(self):
        query = generate_next_chained_query("ApplicationComponent", "SAP ERP")
        errors = gql_validator.validate(query)
        assert not errors, f"GQL errors: {errors}\nQuery:\n{query}"
        assert "NEXT" in query
        # Should have two RETURN statements (one per linear query)
        returns = re.findall(r"RETURN", query, re.IGNORECASE)
        assert len(returns) == 2, f"Expected 2 RETURN clauses, got {len(returns)}"


class TestGQLQueryPatternCoverage:
    """Ensure we can generate valid GQL for all common query patterns."""

    def test_all_entity_types_queryable(self):
        """Every entity type should produce a valid GQL query."""
        for entity_type in ARCHIMATE_ENTITY_TYPES:
            query = generate_find_entity_query(entity_type)
            errors = gql_validator.validate(query)
            assert not errors, f"{entity_type}: {errors}"

    def test_all_relationship_types_queryable(self):
        """Every relationship type should be usable in a MATCH pattern."""
        for rel in ARCHIMATE_RELATIONSHIP_TYPES:
            query = generate_find_related_query(
                "ApplicationComponent", "TestApp", rel, "outgoing"
            )
            errors = gql_validator.validate(query)
            assert not errors, f"{rel}: {errors}"

    def test_all_cross_layer_patterns(self):
        """Key cross-layer queries should be valid."""
        patterns = [
            ("Application", "Business", "Serving"),
            ("Application", "Business", "Realization"),
            ("Technology", "Application", "Serving"),
            ("Motivation", "Business", "Influence"),
        ]
        for src_layer, tgt_layer, rel in patterns:
            query = generate_cross_layer_query(src_layer, tgt_layer, rel)
            errors = gql_validator.validate(query)
            assert not errors, f"{src_layer}->{tgt_layer} via {rel}: {errors}"


class TestSpannerDDLGQLAlignment:
    """Validate that the Spanner DDL defines all labels used in GQL queries."""

    def test_all_node_labels_in_ddl(self, spanner_ddl):
        """Every node label used in GQL should have a CREATE TABLE in the DDL."""
        for label in NODE_LABELS:
            assert f"CREATE TABLE {label}" in spanner_ddl, (
                f"Node label '{label}' used in GQL but not defined in DDL"
            )

    def test_all_edge_labels_in_ddl(self, spanner_ddl):
        """Every edge label used in GQL should have a LABEL in the Property Graph."""
        for label in EDGE_LABELS:
            assert f"LABEL {label}" in spanner_ddl, (
                f"Edge label '{label}' used in GQL but not defined in Property Graph DDL"
            )

    def test_property_graph_defined(self, spanner_ddl):
        assert f"CREATE PROPERTY GRAPH {GRAPH_NAME}" in spanner_ddl

    def test_all_entity_tables_in_property_graph(self, spanner_ddl):
        """All entity tables should be listed as NODE TABLES."""
        # Extract the NODE TABLES block
        pg_match = re.search(
            r"NODE\s+TABLES\s*\((.*?)\)\s*EDGE\s+TABLES",
            spanner_ddl,
            re.DOTALL | re.IGNORECASE,
        )
        assert pg_match, "Could not find NODE TABLES block in Property Graph"
        node_block = pg_match.group(1)
        for label in NODE_LABELS:
            assert label in node_block, (
                f"Table '{label}' not listed in NODE TABLES of Property Graph"
            )

    def test_edge_tables_have_source_type_target_type(self, spanner_ddl):
        """New edge tables (Wave 2) should have source_type and target_type columns."""
        edge_tables = [
            "Composition", "Aggregation", "Assignment", "Realization",
            "Serving", "Access", "Influence", "Association",
            "Triggering", "Flow", "Specialization",
        ]
        for table in edge_tables:
            # Find the CREATE TABLE block for this edge
            pattern = rf"CREATE TABLE {table}\s*\((.*?)\)\s*PRIMARY KEY"
            match = re.search(pattern, spanner_ddl, re.DOTALL | re.IGNORECASE)
            assert match, f"Edge table '{table}' not found in DDL"
            block = match.group(1)
            assert "source_type" in block, (
                f"Edge table '{table}' missing 'source_type' column"
            )
            assert "target_type" in block, (
                f"Edge table '{table}' missing 'target_type' column"
            )
