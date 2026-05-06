import os
import yaml
from pydantic import BaseModel, Field, create_model
from typing import List, Optional, Any, Dict

# --- Static Inter-Agent Communication Models (API wrappers layer) ---
class KnowledgeExtractionInput(BaseModel):
    document_uri: str
    raw_content: str

class QueryIntent(BaseModel):
    user_query: str
    needs_doc_generation: bool = Field(description="True if the user explicitly asks to generate a document, report, or spec.")
    route_to: str = Field(description="Values can be 'SEARCH_AGENT' or 'DOC_AGENT'")

class ImageChunk(BaseModel):
    image_id: str = Field(description="Reference ID (e.g. 'img_0')")
    doc_id: str = Field(description="Document ID in Spanner")
    chunk_id: str = Field(description="Chunk ID in Spanner")
    source_doc: str = Field(description="Document title")
    page_number: Optional[int] = Field(default=None, description="Page number")

class SearchResult(BaseModel):
    semantically_similar_chunks: List[str] = Field(description="Raw text chunks matching vector search")
    graph_connections: List[str] = Field(description="Graph DB traversal strings explaining connections")
    source_documents: List[str] = Field(description="Source document references in 'Title | Page N' format", default_factory=list)
    image_chunks: List[ImageChunk] = Field(description="Image chunks with IDs for frontend fetch", default_factory=list)

class DocumentGenerationOutput(BaseModel):
    document_title: str
    markdown_content: str

# --- Load Dynamic Knowledge Graph Ontology from YAML ---
def load_dynamic_ontology():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    yaml_path = os.path.join(base_dir, "ontology.yaml")

    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"Ontology file missing at {yaml_path}")
        
    with open(yaml_path, 'r', encoding='utf-8') as f:
        ontology_data = yaml.safe_load(f)

    # Simplified Type mapping (Extensible for more Python types)
    type_map = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "Optional[str]": Optional[str],
        "Optional[int]": Optional[int]
    }

    dynamic_entities = {}
    
    # 1. First Pass: Create Entity Models (e.g. ApplicationMetadata, BusinessRequirementMetadata)
    entities = ontology_data.get("entities", {})
    for entity_name, entity_def in entities.items():
        fields = {}
        for field_name, field_def_yaml in entity_def.get("fields", {}).items():
            field_type_str = field_def_yaml.get("type", "str")
            field_attr = type_map.get(field_type_str, str) # Default to str if missing
            
            # Setup the Field with description
            fields[field_name] = (field_attr, Field(description=field_def_yaml.get("description", "")))

        # Create the dynamic Base Model
        model = create_model(entity_name, **fields, __base__=BaseModel)
        model.__doc__ = entity_def.get("description", "")
        dynamic_entities[entity_name] = model

    # Register dynamically created nested entities as List variants in the type map 
    for name, model in dynamic_entities.items():
        type_map[f"List[{name}]"] = List[model]

    # 2. Second Pass: Map Root Object (ExtractedEntities)
    extracted_entities_def = ontology_data.get("extracted_entities", {})
    root_fields = {}
    for field_name, field_def_yaml in extracted_entities_def.get("fields", {}).items():
        field_type_str = field_def_yaml.get("type", "List[Any]")
        field_attr = type_map.get(field_type_str, List[Any])
        
        # Give lists a default factory of an empty list
        if field_type_str.startswith("List["):
            root_fields[field_name] = (field_attr, Field(description=field_def_yaml.get("description", ""), default_factory=list))
        else:
            root_fields[field_name] = (field_attr, Field(description=field_def_yaml.get("description", "")))

    DynExtractedEntities = create_model("ExtractedEntities", **root_fields, __base__=BaseModel)
    DynExtractedEntities.__doc__ = extracted_entities_def.get("description", "")
    
    return DynExtractedEntities, dynamic_entities

# Generate the types dynamically at import time
try:
    ExtractedEntities, DynamicEntities = load_dynamic_ontology()
    
    # We explicitly alias the inner models into module scope for convenience (optional but helpful)
    # E.g., dynamic exports for ApplicationMetadata and BusinessRequirementMetadata
    for ent_name, ent_class in DynamicEntities.items():
        globals()[ent_name] = ent_class

except Exception as e:
    print(f"[ERROR] Could not load dynamic ontology: {e}")
    # Fallback Empty Model if YAML is totally broken (prevents import crash)
    class ExtractedEntities(BaseModel):
        pass
