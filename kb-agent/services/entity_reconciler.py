"""Entity reconciliation engine (iText2KG-inspired).

For each entity extracted from a document, determines whether it already exists
in the Spanner Knowledge Graph via:
1. Exact name match (case-insensitive, fast path)
2. Vector similarity match (cosine distance < threshold)
3. If no match → create new entity with fresh UUID

Reference: iText2KG (arXiv:2409.03284) — cosine threshold 0.85 (distance 0.15)
"""
import os
import uuid
import logging
from google.cloud.spanner_v1 import param_types

from services.schema_registry import ENTITY_TABLE_MAP
from services.tenant_context import SHARED_TENANT

logger = logging.getLogger(__name__)

RECONCILIATION_THRESHOLD = float(os.getenv("RECONCILIATION_THRESHOLD", "0.15"))


class EntityReconciler:
    """Reconciles extracted entities against existing Spanner graph entities.

    Maintains an in-memory cache per session to avoid redundant lookups
    when the same entity appears multiple times in one document.
    """

    def __init__(self, database, tenant_id: str = SHARED_TENANT):
        self._db = database
        self._tenant_id = tenant_id
        self._cache: dict[str, tuple[str, bool]] = {}  # "Type:Name" → (uuid, is_new)
        self._stats = {"exact": 0, "vector": 0, "new": 0, "cached": 0}

    def reconcile(
        self,
        entity_type: str,
        entity_name: str,
        embedding: list[float],
    ) -> tuple[str, bool]:
        """Resolve an entity to an existing or new UUID.

        Args:
            entity_type: ArchiMate type (e.g. "ApplicationComponent")
            entity_name: Entity display name (e.g. "CRM System")
            embedding: 768-dim embedding vector for the entity

        Returns:
            (entity_id, is_new) — UUID of the resolved entity and whether it's new
        """
        cache_key = f"{entity_type}:{entity_name}"

        # Check cache first
        if cache_key in self._cache:
            self._stats["cached"] += 1
            return self._cache[cache_key]

        table_info = ENTITY_TABLE_MAP.get(entity_type)
        if not table_info:
            logger.warning(f"Unknown entity type '{entity_type}', creating new")
            result = (str(uuid.uuid4()), True)
            self._cache[cache_key] = result
            return result

        # Step 1: Exact name match (case-insensitive)
        existing_id = self._exact_match(table_info, entity_name)
        if existing_id:
            self._stats["exact"] += 1
            result = (existing_id, False)
            self._cache[cache_key] = result
            logger.debug(f"Exact match: {cache_key} → {existing_id}")
            return result

        # Step 2: Vector similarity match (skip zero vectors)
        if embedding and any(v != 0.0 for v in embedding):
            similar_id = self._vector_match(table_info, embedding)
            if similar_id:
                self._stats["vector"] += 1
                result = (similar_id, False)
                self._cache[cache_key] = result
                logger.debug(f"Vector match: {cache_key} → {similar_id}")
                return result

        # Step 3: Create new entity
        new_id = str(uuid.uuid4())
        self._stats["new"] += 1
        result = (new_id, True)
        self._cache[cache_key] = result
        logger.debug(f"New entity: {cache_key} → {new_id}")
        return result

    def batch_reconcile(
        self,
        entities: list[dict],
    ) -> dict[str, tuple[str, bool]]:
        """Reconcile a batch of entities.

        Args:
            entities: List of {"type": str, "name": str, "embedding": list[float]}

        Returns:
            Dict of "Type:Name" → (uuid, is_new)
        """
        results = {}
        # Group by type for batch exact-match optimization
        by_type: dict[str, list[dict]] = {}
        for e in entities:
            by_type.setdefault(e["type"], []).append(e)

        for entity_type, type_entities in by_type.items():
            # Batch exact match for this type
            names = [e["name"] for e in type_entities]
            exact_matches = self._batch_exact_match(
                ENTITY_TABLE_MAP.get(entity_type), names
            )

            for e in type_entities:
                cache_key = f"{e['type']}:{e['name']}"
                lower_name = e["name"].lower()

                if lower_name in exact_matches:
                    self._stats["exact"] += 1
                    result = (exact_matches[lower_name], False)
                    self._cache[cache_key] = result
                    results[cache_key] = result
                else:
                    # Fall back to individual reconciliation (vector match)
                    result = self.reconcile(e["type"], e["name"], e.get("embedding", []))
                    results[cache_key] = result

        return results

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    # --- Private methods ---

    def _exact_match(self, table_info: dict, name: str) -> str | None:
        """Find entity by exact name match (case-insensitive), scoped to tenant."""
        sql = (
            f"SELECT {table_info['id_col']} "
            f"FROM {table_info['table']} "
            f"WHERE LOWER({table_info['name_col']}) = @name "
            f"AND tenant_id IN (@tenant_id, @shared_tenant) "
            f"LIMIT 1"
        )
        try:
            with self._db.snapshot() as snapshot:
                result = snapshot.execute_sql(
                    sql,
                    params={"name": name.lower(), "tenant_id": self._tenant_id, "shared_tenant": SHARED_TENANT},
                    param_types={"name": param_types.STRING, "tenant_id": param_types.STRING, "shared_tenant": param_types.STRING},
                )
                row = next(iter(result), None)
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Exact match query failed for {table_info['table']}: {e}")
            return None

    def _batch_exact_match(self, table_info: dict | None, names: list[str]) -> dict[str, str]:
        """Batch exact match for multiple names of the same type.

        Returns:
            Dict of lowercase_name → existing_id
        """
        if not table_info or not names:
            return {}

        sql = (
            f"SELECT {table_info['id_col']}, LOWER({table_info['name_col']}) AS lname "
            f"FROM {table_info['table']} "
            f"WHERE LOWER({table_info['name_col']}) IN UNNEST(@names) "
            f"AND tenant_id IN (@tenant_id, @shared_tenant)"
        )
        lower_names = [n.lower() for n in names]

        try:
            with self._db.snapshot() as snapshot:
                result = snapshot.execute_sql(
                    sql,
                    params={"names": lower_names, "tenant_id": self._tenant_id, "shared_tenant": SHARED_TENANT},
                    param_types={"names": param_types.Array(param_types.STRING), "tenant_id": param_types.STRING, "shared_tenant": param_types.STRING},
                )
                return {row[1]: row[0] for row in result}
        except Exception as e:
            logger.error(f"Batch exact match failed for {table_info['table']}: {e}")
            return {}

    def _vector_match(self, table_info: dict, embedding: list[float]) -> str | None:
        """Find most similar entity by cosine distance on embeddings."""
        emb_col = table_info["embedding_col"]
        sql = (
            f"SELECT {table_info['id_col']}, "
            f"COSINE_DISTANCE({emb_col}, @query_embedding) AS dist "
            f"FROM {table_info['table']} "
            f"WHERE {emb_col} IS NOT NULL "
            f"AND ARRAY_LENGTH({emb_col}) > 0 "
            f"AND {emb_col}[OFFSET(0)] != 0.0 "
            f"AND tenant_id IN (@tenant_id, @shared_tenant) "
            f"ORDER BY dist ASC "
            f"LIMIT 1"
        )
        try:
            with self._db.snapshot() as snapshot:
                result = snapshot.execute_sql(
                    sql,
                    params={"query_embedding": embedding, "tenant_id": self._tenant_id, "shared_tenant": SHARED_TENANT},
                    param_types={"query_embedding": param_types.Array(param_types.FLOAT32), "tenant_id": param_types.STRING, "shared_tenant": param_types.STRING},
                )
                row = next(iter(result), None)
                if row and row[1] < RECONCILIATION_THRESHOLD:
                    return row[0]
                return None
        except Exception as e:
            logger.error(f"Vector match query failed for {table_info['table']}: {e}")
            return None
