"""Entity search: queries existing entities in Spanner Knowledge Graph.

Used by the ProcessingAgent's search_existing_entities tool (STEP 3) to find
entities already present in the graph that relate to the document being processed.

Search strategy:
1. Compute embedding for the query themes
2. Vector similarity search across 5 most common entity tables
3. Aggregate and rank results by cosine distance
4. Return top results as "Type:Name" strings
"""
import logging
from google import genai
from google.cloud.spanner_v1 import param_types

from services.spanner_client import get_database
from services.schema_registry import ENTITY_TABLE_MAP
from services.document_chunker import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
from services.tenant_context import get_tenant, tenant_sql_filter
from services.cost_tracker import get_tracker

logger = logging.getLogger(__name__)

# Tables to search (most commonly populated, ordered by priority)
SEARCH_TABLES = [
    "ApplicationComponent",
    "BusinessProcess",
    "DataObject",
    "Node",
    "SystemSoftware",
    "BusinessActor",
    "Requirement",
    "TechnologyService",
]

TOP_PER_TABLE = 3
TOP_TOTAL = 10


def search_entities_by_themes(query: str) -> list[str]:
    """Search existing entities in Spanner by semantic similarity.

    Args:
        query: Free-text query describing themes/topics to search for

    Returns:
        List of "EntityType:EntityName" strings for matching entities
    """
    # 1. Compute query embedding
    query_embedding = _compute_query_embedding(query)
    if not query_embedding:
        logger.warning("Failed to compute query embedding, returning empty results")
        return []

    # 2. Search across tables
    all_results: list[tuple[str, str, float]] = []  # (type, name, distance)
    database = get_database()

    for entity_type in SEARCH_TABLES:
        table_info = ENTITY_TABLE_MAP.get(entity_type)
        if not table_info:
            continue

        results = _vector_search(database, table_info, entity_type, query_embedding)
        all_results.extend(results)

    # 3. Sort by distance (ascending = most similar first) and take top N
    all_results.sort(key=lambda x: x[2])
    top_results = all_results[:TOP_TOTAL]

    # 4. Format as "Type:Name"
    formatted = [f"{r[0]}:{r[1]}" for r in top_results]
    logger.info(f"Entity search for '{query[:50]}...' found {len(formatted)} results")
    return formatted


def _compute_query_embedding(query: str) -> list[float]:
    """Compute embedding for a search query."""
    try:
        from services.document_chunker import _get_embedding_client
        client = _get_embedding_client()
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=query[:8000],
            config=genai.types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=EMBEDDING_DIMENSIONS,
            ),
        )
        tracker = get_tracker()
        if tracker:
            tracker.track_embed(texts=query[:8000], model=EMBEDDING_MODEL)
        return list(response.embeddings[0].values)
    except Exception as e:
        logger.error(f"Query embedding failed: {e}")
        return []


def _vector_search(
    database, table_info: dict, entity_type: str, query_embedding: list[float]
) -> list[tuple[str, str, float]]:
    """Search a single entity table by vector similarity."""
    _tenant_id = get_tenant()
    sql = (
        f"SELECT {table_info['name_col']}, "
        f"COSINE_DISTANCE({table_info['embedding_col']}, @query_emb) AS dist "
        f"FROM {table_info['table']} "
        f"WHERE {table_info['embedding_col']} IS NOT NULL "
        f"AND {tenant_sql_filter()} "
        f"ORDER BY dist ASC "
        f"LIMIT {TOP_PER_TABLE}"
    )
    try:
        with database.snapshot() as snapshot:
            result = snapshot.execute_sql(
                sql,
                params={"query_emb": query_embedding, "_tid": _tenant_id},
                param_types={"query_emb": param_types.Array(param_types.FLOAT32), "_tid": param_types.STRING},
            )
            rows = [(entity_type, row[0], row[1]) for row in result]
            tracker = get_tracker()
            if tracker:
                tracker.track_spanner_read()
            return rows
    except Exception as e:
        logger.debug(f"Vector search on {table_info['table']} failed (table may be empty): {e}")
        return []
