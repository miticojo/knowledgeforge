"""
Test Suite 4: End-to-End Extraction Scenarios
Tests realistic document-to-graph extraction pipelines, validating the full chain:
Document Text -> Entity Classification -> Relationship Extraction -> GQL Compliance.

These tests simulate what the ProcessingAgent does: given raw document text,
validate that the expected ArchiMate graph is correct and GQL-queryable.
"""
import re
import pytest

from tests.conftest import (
    ARCHIMATE_ENTITY_TYPES,
    ARCHIMATE_RELATIONSHIP_TYPES,
    ENTITY_LAYER_MAP,
)
from tests.test_graph_extraction import (
    parse_node,
    parse_edge,
    validate_relationship_semantics,
)
from tests.test_spanner_gql_syntax import (
    GRAPH_NAME,
    ENTITY_TO_LABEL,
    gql_validator,
    _name_field,
)


# ---------------------------------------------------------------------------
# Full extraction scenario definition
# ---------------------------------------------------------------------------

class ExtractionScenario:
    """A complete document-to-graph extraction scenario."""

    def __init__(
        self,
        name: str,
        document_text: str,
        expected_nodes: list[str],
        expected_edges: list[str],
        expected_gql_queries: list[str] | None = None,
    ):
        self.name = name
        self.document_text = document_text
        self.expected_nodes = expected_nodes
        self.expected_edges = expected_edges
        self.expected_gql_queries = expected_gql_queries or []

    def validate(self) -> list[str]:
        """Run all validations. Return list of errors."""
        errors = []

        # 1. Validate all nodes
        node_keys = set()
        for n in self.expected_nodes:
            try:
                t, name = parse_node(n)
                if t not in ARCHIMATE_ENTITY_TYPES:
                    errors.append(f"[{self.name}] Invalid entity type in node: '{t}'")
                node_keys.add(f"{t}:{name}")
            except ValueError as e:
                errors.append(f"[{self.name}] Node parse error: {e}")

        # 2. Validate all edges
        for e_str in self.expected_edges:
            try:
                edge = parse_edge(e_str)

                # Check types are valid
                if edge["source_type"] not in ARCHIMATE_ENTITY_TYPES:
                    errors.append(f"[{self.name}] Invalid source type: '{edge['source_type']}'")
                if edge["target_type"] not in ARCHIMATE_ENTITY_TYPES:
                    errors.append(f"[{self.name}] Invalid target type: '{edge['target_type']}'")
                if edge["relationship_type"] not in ARCHIMATE_RELATIONSHIP_TYPES:
                    errors.append(f"[{self.name}] Invalid relationship: '{edge['relationship_type']}'")

                # Check referential integrity
                src_key = f"{edge['source_type']}:{edge['source_name']}"
                tgt_key = f"{edge['target_type']}:{edge['target_name']}"
                if src_key not in node_keys:
                    errors.append(f"[{self.name}] Dangling edge source: '{src_key}'")
                if tgt_key not in node_keys:
                    errors.append(f"[{self.name}] Dangling edge target: '{tgt_key}'")

                # Semantic validation
                sem_errors = validate_relationship_semantics(edge)
                for se in sem_errors:
                    errors.append(f"[{self.name}] Semantic: {se}")

            except ValueError as e:
                errors.append(f"[{self.name}] Edge parse error: {e}")

        # 3. Validate GQL queries
        for q in self.expected_gql_queries:
            gql_errors = gql_validator.validate(q)
            for ge in gql_errors:
                errors.append(f"[{self.name}] GQL: {ge}")

        return errors


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

SCENARIO_INFRA_MIGRATION = ExtractionScenario(
    name="Infrastructure Migration Document",
    document_text="""
    Documento: Migrazione Infrastruttura CRM

    Il sistema CRM attuale gira su server Dell PowerEdge R740 con Red Hat Linux 8
    e Oracle Database 19c. L'applicazione CRM è un monolite Java deployato come
    crm-app.war su Apache Tomcat 9.

    La migrazione prevede lo spostamento su un cluster Kubernetes (GKE) nella
    region europe-west1. Il nuovo deployment utilizzerà container Docker con
    immagini gestite tramite Artifact Registry.

    Il team IT Operations è responsabile della migrazione. L'obiettivo è ridurre
    il TCO del 30% entro Q4 2025. Il vincolo principale è che i dati devono
    rimanere in data center europei per compliance GDPR.

    L'applicazione CRM serve il processo di Customer Onboarding e accede ai
    dati dei clienti (Customer Record) e ai dati delle fatture (Invoice Data).
    """,
    expected_nodes=[
        "ApplicationComponent:CRM System",
        "Node:Dell PowerEdge R740",
        "SystemSoftware:Red Hat Linux 8",
        "SystemSoftware:Oracle Database 19c",
        "SystemSoftware:Apache Tomcat 9",
        "Artifact:crm-app.war",
        "Node:GKE Cluster europe-west1",
        "SystemSoftware:Docker",
        "BusinessActor:IT Operations",
        "Goal:Reduce TCO by 30%",
        "Constraint:Data must remain in European data centers (GDPR)",
        "BusinessProcess:Customer Onboarding",
        "DataObject:Customer Record",
        "DataObject:Invoice Data",
        "TechnologyService:Container Registry",
        "CommunicationNetwork:europe-west1 VPC",
    ],
    expected_edges=[
        "Node:Dell PowerEdge R740->Composition->SystemSoftware:Red Hat Linux 8",
        "SystemSoftware:Red Hat Linux 8->Assignment->SystemSoftware:Apache Tomcat 9",
        "SystemSoftware:Apache Tomcat 9->Assignment->Artifact:crm-app.war",
        "Artifact:crm-app.war->Realization->ApplicationComponent:CRM System",
        "ApplicationComponent:CRM System->Serving->BusinessProcess:Customer Onboarding",
        "ApplicationComponent:CRM System->Access[Read]->DataObject:Customer Record",
        "ApplicationComponent:CRM System->Access[Read]->DataObject:Invoice Data",
        "BusinessActor:IT Operations->Assignment->BusinessProcess:Customer Onboarding",
        "ApplicationComponent:CRM System->Realization->Goal:Reduce TCO by 30%",
        "Constraint:Data must remain in European data centers (GDPR)->Influence[-]->Goal:Reduce TCO by 30%",
    ],
    expected_gql_queries=[
        # Find all apps served by a technology service
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (ts:TechnologyServices)-[e:Serving]->(app:ApplicationComponents)\n"
        f"  RETURN ts.service_name, app.app_name",
        # Find the full deployment stack for CRM
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (art:Artifacts)-[r:Realization]->(app:ApplicationComponents)\n"
        f"  WHERE app.app_name = 'CRM System'\n"
        f"  RETURN art.artifact_name, app.app_name",
    ],
)

SCENARIO_APPLICATION_LANDSCAPE = ExtractionScenario(
    name="Application Landscape Document",
    document_text="""
    Application Landscape Overview

    Il sistema di Billing (Billing Platform) è il cuore dell'ecosistema IT.
    Espone un servizio di fatturazione (Billing API) tramite interfaccia REST.
    Il Billing Platform accede al database fatture (Invoice Database) gestito
    da Oracle Database su un cluster dedicato.

    Il CRM System utilizza il servizio di fatturazione per gestire il processo
    di gestione clienti. Il CRM espone a sua volta un Customer Management API.

    Il team Finance è responsabile del processo di fatturazione. L'Enterprise
    Architect supervisiona l'intera architettura applicativa.

    Il contratto SLA Premium garantisce un uptime del 99.9% per il Billing Platform.
    L'obiettivo strategico è migliorare l'integrazione tra i sistemi.
    """,
    expected_nodes=[
        "ApplicationComponent:Billing Platform",
        "ApplicationService:Billing API",
        "ApplicationInterface:REST Billing Endpoint",
        "ApplicationComponent:CRM System",
        "ApplicationService:Customer Management API",
        "SystemSoftware:Oracle Database",
        "DataObject:Invoice Database",
        "BusinessActor:Finance Team",
        "BusinessProcess:Billing Process",
        "BusinessProcess:Customer Management",
        "Stakeholder:Enterprise Architect",
        "Contract:SLA Premium",
        "Goal:Improve System Integration",
        "Node:Billing DB Cluster",
    ],
    expected_edges=[
        "ApplicationComponent:Billing Platform->Realization->ApplicationService:Billing API",
        "ApplicationComponent:CRM System->Serving->BusinessProcess:Customer Management",
        "ApplicationComponent:CRM System->Realization->ApplicationService:Customer Management API",
        "ApplicationService:Billing API->Serving->ApplicationComponent:CRM System",
        "ApplicationComponent:Billing Platform->Access[ReadWrite]->DataObject:Invoice Database",
        "SystemSoftware:Oracle Database->Serving->ApplicationComponent:Billing Platform",
        "Node:Billing DB Cluster->Assignment->SystemSoftware:Oracle Database",
        "BusinessActor:Finance Team->Assignment->BusinessProcess:Billing Process",
        "ApplicationComponent:Billing Platform->Serving->BusinessProcess:Billing Process",
        "Stakeholder:Enterprise Architect->Influence[+]->Goal:Improve System Integration",
    ],
    expected_gql_queries=[
        # Find all services exposed by an application
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (app:ApplicationComponents)-[r:Realization]->(svc:ApplicationServices)\n"
        f"  RETURN app.app_name, svc.service_name",
        # Find what business processes are served by apps
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (app:ApplicationComponents)-[s:Serving]->(bp:BusinessProcesses)\n"
        f"  RETURN app.app_name, bp.process_name",
        # Impact analysis: what depends on Oracle Database
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (sw:SystemSoftwares)-[e:Serving]->(app:ApplicationComponents)\n"
        f"  WHERE sw.software_name = 'Oracle Database'\n"
        f"  RETURN app.app_name AS dependent_app",
    ],
)

SCENARIO_GOVERNANCE_REQUIREMENTS = ExtractionScenario(
    name="Governance and Requirements Document",
    document_text="""
    IT Governance Framework

    Il CTO richiede che tutti i nuovi sistemi adottino un'architettura a microservizi.
    L'obiettivo principale è aumentare l'agilità del delivery (Goal: Increase Delivery Agility).

    Requisiti chiave:
    - REQ-001: Tutti i servizi devono esporre API REST documentate
    - REQ-002: I dati sensibili devono essere crittografati at rest e in transit
    - REQ-003: Ogni servizio deve avere health check endpoint

    Vincoli architetturali:
    - Il budget annuale per l'infrastruttura non può superare 2M EUR
    - Devono essere utilizzati esclusivamente servizi cloud GCP

    La capability di Cloud Operations è fondamentale per il successo.
    Il team Platform Engineering gestisce la piattaforma Kubernetes.
    La funzione IT Governance supervisiona la compliance.
    """,
    expected_nodes=[
        "Stakeholder:CTO",
        "Goal:Increase Delivery Agility",
        "Requirement:All services must expose documented REST APIs",
        "Requirement:Sensitive data must be encrypted at rest and in transit",
        "Requirement:Every service must have health check endpoint",
        "Constraint:Annual infrastructure budget max 2M EUR",
        "Constraint:Must use GCP cloud services exclusively",
        "Capability:Cloud Operations",
        "BusinessActor:Platform Engineering",
        "BusinessFunction:IT Governance",
        "Node:Kubernetes Platform",
    ],
    expected_edges=[
        "Stakeholder:CTO->Influence[+]->Goal:Increase Delivery Agility",
        "Goal:Increase Delivery Agility->Influence[+]->Requirement:All services must expose documented REST APIs",
        "Goal:Increase Delivery Agility->Influence[+]->Requirement:Every service must have health check endpoint",
        "Constraint:Annual infrastructure budget max 2M EUR->Influence[-]->Goal:Increase Delivery Agility",
        "Constraint:Must use GCP cloud services exclusively->Influence[+]->Requirement:Sensitive data must be encrypted at rest and in transit",
        "BusinessActor:Platform Engineering->Assignment->Node:Kubernetes Platform",
    ],
    expected_gql_queries=[
        # Find all goals influenced by stakeholders
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (s:Stakeholders)-[i:Influence]->(g:Goals)\n"
        f"  RETURN s.stakeholder_name, g.goal_name",
        # Find requirements influenced by goals
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (g:Goals)-[i:Influence]->(r:Requirements)\n"
        f"  RETURN g.goal_name, r.title AS requirement",
        # Find all constraints
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (c:Constraints)\n"
        f"  RETURN c.constraint_name, c.description",
    ],
)

SCENARIO_DATA_ARCHITECTURE = ExtractionScenario(
    name="Data Architecture Document",
    document_text="""
    Data Architecture - Domain: Customer 360

    Il dominio Customer 360 gestisce la vista unificata del cliente.
    Il concetto di business "Cliente" (BusinessObject) è realizzato dal
    DataObject "Customer Master Record" nel sistema CRM e dal
    DataObject "Billing Customer Profile" nel sistema di Billing.

    Il processo di Data Quality Management garantisce la consistenza dei dati.
    La funzione Data Governance supervisiona le policy di data management.
    Il Data Steward è responsabile della qualità dei dati.

    Il CRM System accede in lettura/scrittura al Customer Master Record.
    Il Billing Platform accede in sola lettura al Billing Customer Profile.
    Un flusso dati (Flow) sincronizza i dati dal CRM al Billing Platform.
    """,
    expected_nodes=[
        "BusinessObject:Customer",
        "DataObject:Customer Master Record",
        "DataObject:Billing Customer Profile",
        "ApplicationComponent:CRM System",
        "ApplicationComponent:Billing Platform",
        "BusinessProcess:Data Quality Management",
        "BusinessFunction:Data Governance",
        "BusinessRole:Data Steward",
    ],
    expected_edges=[
        "DataObject:Customer Master Record->Realization->BusinessObject:Customer",
        "DataObject:Billing Customer Profile->Realization->BusinessObject:Customer",
        "ApplicationComponent:CRM System->Access[ReadWrite]->DataObject:Customer Master Record",
        "ApplicationComponent:Billing Platform->Access[Read]->DataObject:Billing Customer Profile",
        "ApplicationComponent:CRM System->Flow->ApplicationComponent:Billing Platform",
        "BusinessRole:Data Steward->Assignment->BusinessProcess:Data Quality Management",
        "BusinessFunction:Data Governance->Aggregation->BusinessProcess:Data Quality Management",
    ],
    expected_gql_queries=[
        # Find what DataObjects realize a BusinessObject
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (d:DataObjects)-[r:Realization]->(bo:BusinessObjects)\n"
        f"  WHERE bo.object_name = 'Customer'\n"
        f"  RETURN d.model_name AS data_object, bo.object_name AS business_concept",
        # Find all data accessed by an application
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (app:ApplicationComponents)-[a:Access]->(d:DataObjects)\n"
        f"  WHERE app.app_name = 'CRM System'\n"
        f"  RETURN d.model_name, a.access_type",
        # Trace data flow between applications
        f"GRAPH {GRAPH_NAME}\n"
        f"  MATCH (src:ApplicationComponents)-[f:Flow]->(tgt:ApplicationComponents)\n"
        f"  RETURN src.app_name AS source, tgt.app_name AS target, f.flow_label",
    ],
)


ALL_SCENARIOS = [
    SCENARIO_INFRA_MIGRATION,
    SCENARIO_APPLICATION_LANDSCAPE,
    SCENARIO_GOVERNANCE_REQUIREMENTS,
    SCENARIO_DATA_ARCHITECTURE,
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractionScenariosValidation:
    """Run full validation on each extraction scenario."""

    @pytest.mark.parametrize(
        "scenario", ALL_SCENARIOS, ids=[s.name for s in ALL_SCENARIOS]
    )
    def test_scenario_validates(self, scenario):
        errors = scenario.validate()
        assert not errors, (
            f"Scenario '{scenario.name}' has {len(errors)} validation errors:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


class TestExtractionCoverage:
    """Validate that scenarios collectively cover all ArchiMate aspects."""

    def test_all_layers_covered(self):
        """Scenarios should collectively cover all 5 layers."""
        layers_seen = set()
        for scenario in ALL_SCENARIOS:
            for n in scenario.expected_nodes:
                t, _ = parse_node(n)
                layer = ENTITY_LAYER_MAP.get(t)
                if layer:
                    layers_seen.add(layer)
        expected_layers = {"Strategy", "Business", "Application", "Technology", "Motivation"}
        missing = expected_layers - layers_seen
        assert not missing, f"Layers not covered by any scenario: {missing}"

    def test_minimum_entity_types_covered(self):
        """Scenarios should use at least 18 of the 22 entity types (80%)."""
        types_seen = set()
        for scenario in ALL_SCENARIOS:
            for n in scenario.expected_nodes:
                t, _ = parse_node(n)
                types_seen.add(t)
        coverage = len(types_seen) / len(ARCHIMATE_ENTITY_TYPES)
        assert coverage >= 0.80, (
            f"Only {len(types_seen)}/{len(ARCHIMATE_ENTITY_TYPES)} entity types "
            f"covered ({coverage:.0%}). Missing: {ARCHIMATE_ENTITY_TYPES - types_seen}"
        )

    def test_minimum_relationship_types_covered(self):
        """Scenarios should use at least 8 of the 11 relationship types (73%)."""
        rels_seen = set()
        for scenario in ALL_SCENARIOS:
            for e in scenario.expected_edges:
                edge = parse_edge(e)
                rels_seen.add(edge["relationship_type"])
        coverage = len(rels_seen) / len(ARCHIMATE_RELATIONSHIP_TYPES)
        assert coverage >= 0.70, (
            f"Only {len(rels_seen)}/{len(ARCHIMATE_RELATIONSHIP_TYPES)} relationship types "
            f"covered ({coverage:.0%}). Missing: {ARCHIMATE_RELATIONSHIP_TYPES - rels_seen}"
        )

    def test_cross_layer_edges_present(self):
        """At least some edges should cross ArchiMate layers."""
        cross_layer_count = 0
        for scenario in ALL_SCENARIOS:
            for e_str in scenario.expected_edges:
                edge = parse_edge(e_str)
                src_layer = ENTITY_LAYER_MAP.get(edge["source_type"])
                tgt_layer = ENTITY_LAYER_MAP.get(edge["target_type"])
                if src_layer and tgt_layer and src_layer != tgt_layer:
                    cross_layer_count += 1
        assert cross_layer_count >= 8, (
            f"Only {cross_layer_count} cross-layer edges across all scenarios (expected >= 8)"
        )


class TestGQLQueryCompleteness:
    """Validate GQL queries in scenarios are syntactically correct."""

    @pytest.mark.parametrize(
        "scenario", ALL_SCENARIOS, ids=[s.name for s in ALL_SCENARIOS]
    )
    def test_scenario_gql_queries_valid(self, scenario):
        for i, query in enumerate(scenario.expected_gql_queries):
            errors = gql_validator.validate(query)
            assert not errors, (
                f"[{scenario.name}] GQL query #{i} has errors:\n{errors}\n"
                f"Query:\n{query}"
            )

    def test_gql_covers_core_patterns(self):
        """Collective GQL queries should cover the most important patterns."""
        all_queries = []
        for s in ALL_SCENARIOS:
            all_queries.extend(s.expected_gql_queries)

        patterns_found = {
            "simple_match": False,
            "filtered_match": False,
            "multi_node_label": False,
        }

        for q in all_queries:
            if "WHERE" in q:
                patterns_found["filtered_match"] = True
            # Multi node label = query references 2+ different node labels
            node_labels_in_q = re.findall(r"\(\w+:(\w+)\)", q)
            if len(set(node_labels_in_q)) >= 2:
                patterns_found["multi_node_label"] = True
            if "MATCH" in q:
                patterns_found["simple_match"] = True

        for pattern, found in patterns_found.items():
            assert found, f"GQL pattern '{pattern}' not covered by any scenario query"


class TestEdgeDirectionConsistency:
    """Validate that edge directions are consistent across scenarios."""

    def test_serving_direction_provider_to_consumer(self):
        """Serving edges: provider -> consumer (lower layer serves higher)."""
        layer_order = {"Technology": 0, "Application": 1, "Business": 2}
        for scenario in ALL_SCENARIOS:
            for e_str in scenario.expected_edges:
                edge = parse_edge(e_str)
                if edge["relationship_type"] != "Serving":
                    continue
                src_layer = ENTITY_LAYER_MAP.get(edge["source_type"])
                tgt_layer = ENTITY_LAYER_MAP.get(edge["target_type"])
                if src_layer in layer_order and tgt_layer in layer_order:
                    # Cross-layer serving: source should be same or lower layer
                    src_ord = layer_order[src_layer]
                    tgt_ord = layer_order[tgt_layer]
                    assert src_ord <= tgt_ord, (
                        f"Serving direction wrong: {edge['source_type']}({src_layer}) "
                        f"-> {edge['target_type']}({tgt_layer}). "
                        f"Lower layer should serve higher layer."
                    )

    def test_assignment_direction_structure_to_behavior(self):
        """Assignment: active structure -> behavior (or actor -> role)."""
        active_structure = {
            "BusinessActor", "BusinessRole", "Node", "Device",
            "SystemSoftware", "ApplicationComponent",
        }
        for scenario in ALL_SCENARIOS:
            for e_str in scenario.expected_edges:
                edge = parse_edge(e_str)
                if edge["relationship_type"] != "Assignment":
                    continue
                # Source should generally be active structure
                if edge["source_type"] not in active_structure:
                    pytest.fail(
                        f"Assignment source '{edge['source_type']}' is not an "
                        f"active structure element in: {e_str}"
                    )
