"""ArchiMate 3.2 ↔ Spanner Schema Registry.

Single source of truth for mapping ArchiMate entity types to Spanner table names,
column names, and ArchiMate layer assignments.
"""

# --- Entity Type → Spanner Table mapping (22 entries) ---
# Each entry maps an ArchiMate entity type to its Spanner table details:
# table: Spanner table name, id_col: primary key column, name_col: display name column,
# embedding_col: vector embedding column
ENTITY_TABLE_MAP: dict[str, dict[str, str]] = {
    # Strategy Layer
    "Capability": {"table": "Capabilities", "id_col": "capability_id", "name_col": "capability_name", "embedding_col": "capability_embedding"},
    # Business Layer
    "BusinessActor": {"table": "BusinessActors", "id_col": "actor_id", "name_col": "actor_name", "embedding_col": "actor_embedding"},
    "BusinessRole": {"table": "BusinessRoles", "id_col": "role_id", "name_col": "role_name", "embedding_col": "role_embedding"},
    "BusinessProcess": {"table": "BusinessProcesses", "id_col": "process_id", "name_col": "process_name", "embedding_col": "process_embedding"},
    "BusinessFunction": {"table": "BusinessFunctions", "id_col": "function_id", "name_col": "function_name", "embedding_col": "function_embedding"},
    "BusinessService": {"table": "BusinessServices", "id_col": "service_id", "name_col": "service_name", "embedding_col": "service_embedding"},
    "BusinessObject": {"table": "BusinessObjects", "id_col": "object_id", "name_col": "object_name", "embedding_col": "object_embedding"},
    "Contract": {"table": "Contracts", "id_col": "contract_id", "name_col": "contract_name", "embedding_col": "contract_embedding"},
    # Application Layer
    "ApplicationComponent": {"table": "ApplicationComponents", "id_col": "app_id", "name_col": "app_name", "embedding_col": "app_embedding"},
    "ApplicationService": {"table": "ApplicationServices", "id_col": "service_id", "name_col": "service_name", "embedding_col": "service_embedding"},
    "ApplicationInterface": {"table": "ApplicationInterfaces", "id_col": "interface_id", "name_col": "interface_name", "embedding_col": "interface_embedding"},
    "DataObject": {"table": "DataObjects", "id_col": "model_id", "name_col": "model_name", "embedding_col": "model_embedding"},
    # Technology Layer
    "Node": {"table": "Nodes", "id_col": "node_id", "name_col": "node_name", "embedding_col": "node_embedding"},
    "Device": {"table": "Devices", "id_col": "device_id", "name_col": "device_name", "embedding_col": "device_embedding"},
    "SystemSoftware": {"table": "SystemSoftwares", "id_col": "software_id", "name_col": "software_name", "embedding_col": "software_embedding"},
    "TechnologyService": {"table": "TechnologyServices", "id_col": "service_id", "name_col": "service_name", "embedding_col": "service_embedding"},
    "Artifact": {"table": "Artifacts", "id_col": "artifact_id", "name_col": "artifact_name", "embedding_col": "artifact_embedding"},
    "CommunicationNetwork": {"table": "CommunicationNetworks", "id_col": "network_id", "name_col": "network_name", "embedding_col": "network_embedding"},
    # Motivation Layer
    "Goal": {"table": "Goals", "id_col": "goal_id", "name_col": "goal_name", "embedding_col": "goal_embedding"},
    "Requirement": {"table": "Requirements", "id_col": "req_id", "name_col": "title", "embedding_col": "req_embedding"},
    "Constraint": {"table": "Constraints", "id_col": "constraint_id", "name_col": "constraint_name", "embedding_col": "constraint_embedding"},
    "Stakeholder": {"table": "Stakeholders", "id_col": "stakeholder_id", "name_col": "stakeholder_name", "embedding_col": "stakeholder_embedding"},
}

# --- Relationship Type → Edge Table mapping (11 entries) ---
EDGE_TABLE_MAP: dict[str, dict[str, str]] = {
    "Composition":    {"table": "Composition",    "detail_col": "details",              "confidence_col": "confidence"},
    "Aggregation":    {"table": "Aggregation",    "detail_col": "details",              "confidence_col": "confidence"},
    "Assignment":     {"table": "Assignment",     "detail_col": "role_name",            "confidence_col": "confidence"},
    "Realization":    {"table": "Realization",    "detail_col": "details",              "confidence_col": "confidence"},
    "Serving":        {"table": "Serving",        "detail_col": "serving_details",      "confidence_col": "confidence"},
    "Access":         {"table": "Access",         "detail_col": "access_type",          "confidence_col": "confidence"},
    "Influence":      {"table": "Influence",      "detail_col": "influence_strength",   "confidence_col": "confidence"},
    "Association":    {"table": "Association",     "detail_col": "association_details",  "confidence_col": "confidence"},
    "Triggering":     {"table": "Triggering",     "detail_col": "details",              "confidence_col": "confidence"},
    "Flow":           {"table": "Flow",           "detail_col": "flow_label",           "confidence_col": "confidence"},
    "Specialization": {"table": "Specialization", "detail_col": "details",              "confidence_col": "confidence"},
}

# --- Entity Type → ArchiMate Layer ---
ARCHIMATE_LAYER_MAP: dict[str, str] = {
    "Capability": "Strategy",
    "BusinessActor": "Business", "BusinessRole": "Business",
    "BusinessProcess": "Business", "BusinessFunction": "Business",
    "BusinessService": "Business", "BusinessObject": "Business", "Contract": "Business",
    "ApplicationComponent": "Application", "ApplicationService": "Application",
    "ApplicationInterface": "Application", "DataObject": "Application",
    "Node": "Technology", "Device": "Technology", "SystemSoftware": "Technology",
    "TechnologyService": "Technology", "Artifact": "Technology",
    "CommunicationNetwork": "Technology",
    "Goal": "Motivation", "Requirement": "Motivation",
    "Constraint": "Motivation", "Stakeholder": "Motivation",
}

# Canonical sets for validation
VALID_ENTITY_TYPES = frozenset(ENTITY_TABLE_MAP.keys())
VALID_RELATIONSHIP_TYPES = frozenset(EDGE_TABLE_MAP.keys())
VALID_LAYERS = frozenset(ARCHIMATE_LAYER_MAP.values())
