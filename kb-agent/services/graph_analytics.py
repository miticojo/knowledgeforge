"""Graph analytics: god nodes, stats, conformance checking, and impact analysis."""
import logging
import os
from collections import Counter, deque
from services.schema_registry import ENTITY_TABLE_MAP, EDGE_TABLE_MAP, ARCHIMATE_LAYER_MAP
from services.tenant_context import get_tenant, tenant_sql_filter, tenant_sql_filter_for

logger = logging.getLogger(__name__)


def _tenant_params(tid: str | None = None) -> tuple[dict, dict]:
    """Return (params, param_types) for tenant filtering."""
    _tid = tid if tid is not None else get_tenant()
    return {"_tid": _tid}, {"_tid": _string_param_type()}


def get_god_nodes(database, top_n: int = 10, tenant_id: str | None = None) -> list[dict]:
    """Return the most-connected entities across all edge tables.

    Queries each edge table for source_id and target_id, counts degree per entity,
    then resolves names from entity tables. Sorted by degree descending.
    """
    tp, tt = _tenant_params(tenant_id)
    degree_counter: Counter = Counter()
    entity_type_map: dict[str, str] = {}  # entity_id -> source_type or target_type

    for rel_type, einfo in EDGE_TABLE_MAP.items():
        try:
            with database.snapshot() as snap:
                rows = snap.execute_sql(
                    f"SELECT source_id, source_type, target_id, target_type FROM {einfo['table']} WHERE {tenant_sql_filter_for(database, einfo['table'])}",
                    params=tp, param_types=tt,
                )
                for row in rows:
                    src_id, src_type, tgt_id, tgt_type = row[0], row[1], row[2], row[3]
                    if src_id:
                        degree_counter[src_id] += 1
                        if src_type:
                            entity_type_map[src_id] = src_type
                    if tgt_id:
                        degree_counter[tgt_id] += 1
                        if tgt_type:
                            entity_type_map[tgt_id] = tgt_type
        except Exception as e:
            logger.debug(f"Error querying {einfo['table']}: {e}")

    # Get top-N by degree
    top_entities = degree_counter.most_common(top_n * 2)  # Fetch extra to account for resolution failures

    # Resolve names
    results = []
    for entity_id, degree in top_entities:
        if len(results) >= top_n:
            break
        entity_type = entity_type_map.get(entity_id, "")
        tinfo = ENTITY_TABLE_MAP.get(entity_type)
        if not tinfo:
            continue
        try:
            with database.snapshot() as snap:
                name_rows = snap.execute_sql(
                    f"SELECT {tinfo['name_col']} FROM {tinfo['table']} WHERE {tinfo['id_col']} = @eid AND {tenant_sql_filter_for(database, tinfo['table'])}",
                    params={"eid": entity_id, **tp},
                    param_types={"eid": _string_param_type(), **tt},
                )
                for r in name_rows:
                    if r[0]:
                        results.append({
                            "entity_id": entity_id,
                            "name": r[0],
                            "type": entity_type,
                            "degree": degree,
                        })
                    break
        except Exception:
            pass

    return results


def get_graph_stats(database, tenant_id: str | None = None) -> dict:
    """Return aggregate statistics for the knowledge graph."""
    tp, tt = _tenant_params(tenant_id)
    total_entities = 0
    entities_by_type = {}

    for etype, tinfo in ENTITY_TABLE_MAP.items():
        try:
            with database.snapshot() as snap:
                rows = snap.execute_sql(
                    f"SELECT COUNT(*) FROM {tinfo['table']} WHERE {tenant_sql_filter_for(database, tinfo['table'])}",
                    params=tp, param_types=tt,
                )
                for r in rows:
                    count = r[0]
                    if count > 0:
                        entities_by_type[etype] = count
                        total_entities += count
        except Exception:
            pass

    total_edges = 0
    edges_by_type = {}
    confidence_totals = {"EXTRACTED": 0, "INFERRED": 0, "AMBIGUOUS": 0, "NULL": 0}

    for rel_type, einfo in EDGE_TABLE_MAP.items():
        try:
            with database.snapshot() as snap:
                rows = snap.execute_sql(
                    f"SELECT confidence, COUNT(*) FROM {einfo['table']} WHERE {tenant_sql_filter_for(database, einfo['table'])} GROUP BY confidence",
                    params=tp, param_types=tt,
                )
                type_total = 0
                for r in rows:
                    conf = r[0] if r[0] else "NULL"
                    count = r[1]
                    type_total += count
                    if conf in confidence_totals:
                        confidence_totals[conf] += count
                if type_total > 0:
                    edges_by_type[rel_type] = type_total
                    total_edges += type_total
        except Exception:
            pass

    # Document count
    doc_count = 0
    chunk_count = 0
    try:
        with database.snapshot() as snap:
            for r in snap.execute_sql(
                f"SELECT COUNT(*) FROM Documents WHERE {tenant_sql_filter_for(database, 'Documents')}",
                params=tp, param_types=tt,
            ):
                doc_count = r[0]
        with database.snapshot() as snap:
            for r in snap.execute_sql(
                f"SELECT COUNT(*) FROM DocumentChunks WHERE {tenant_sql_filter_for(database, 'DocumentChunks')}",
                params=tp, param_types=tt,
            ):
                chunk_count = r[0]
    except Exception:
        pass

    return {
        "total_entities": total_entities,
        "entities_by_type": entities_by_type,
        "total_edges": total_edges,
        "edges_by_type": edges_by_type,
        "confidence_distribution": confidence_totals,
        "documents": doc_count,
        "chunks": chunk_count,
    }


def _string_param_type():
    from google.cloud.spanner_v1 import param_types
    return param_types.STRING


# ---------------------------------------------------------------------------
# Conformance Checking
# ---------------------------------------------------------------------------

def _load_rules() -> list[dict]:
    """Load architecture rules from YAML config."""
    import yaml
    rules_path = os.path.join(os.path.dirname(__file__), "..", "config", "architecture_rules.yaml")
    with open(rules_path) as f:
        return yaml.safe_load(f).get("rules", [])


def check_conformance(database, tenant_id: str | None = None) -> dict:
    """Validate the knowledge graph against architecture rules.

    Returns a report with pass/warning/error counts and per-rule results.
    """
    tp, tt = _tenant_params(tenant_id)
    rules = _load_rules()
    results = []

    for rule in rules:
        try:
            result = _check_rule(database, rule, tp, tt)
        except Exception as e:
            result = {
                "rule_id": rule["id"],
                "description": rule["description"],
                "severity": rule.get("severity", "info"),
                "status": "error",
                "violations": [f"Rule check failed: {e}"],
                "violation_count": None,
            }
        results.append(result)

    passed = sum(1 for r in results if r["status"] == "passed")
    warnings = sum(1 for r in results if r["status"] == "violated" and r["severity"] == "warning")
    errors = sum(1 for r in results if r["status"] == "violated" and r["severity"] == "error")

    return {
        "total_rules": len(results),
        "passed": passed,
        "warnings": warnings,
        "errors": errors,
        "results": results,
    }


def _check_rule(database, rule: dict, tp: dict, tt: dict) -> dict:
    """Dispatch rule check by type."""
    rtype = rule["type"]
    base = {
        "rule_id": rule["id"],
        "description": rule["description"],
        "severity": rule.get("severity", "info"),
    }

    if rtype == "minimum_connections":
        violations = _check_minimum_connections(database, rule, tp, tt)
    elif rtype == "forbidden_edge":
        violations = _check_forbidden_edge(database, rule, tp, tt)
    elif rtype == "no_orphans":
        violations = _check_orphans(database, tp, tt)
    elif rtype == "ambiguous_only":
        violations = _check_ambiguous_only(database, tp, tt)
    elif rtype == "high_fan_in":
        violations = _check_high_fan_in(database, rule, tp, tt)
    elif rtype == "min_entities_per_doc":
        violations = _check_min_entities_per_doc(database, rule, tp, tt)
    elif rtype == "layer_coverage":
        violations = _check_layer_coverage(database, rule, tp, tt)
    else:
        violations = [f"Unknown rule type: {rtype}"]

    base["status"] = "passed" if not violations else "violated"
    base["violations"] = violations[:20]  # cap output size
    base["violation_count"] = len(violations)
    return base


def _check_minimum_connections(database, rule: dict, tp: dict, tt: dict) -> list[str]:
    """Check that entities of a given type have at least min_count edges of a relationship type."""
    etype = rule["entity_type"]
    rel_type = rule["relationship_type"]
    direction = rule.get("direction", "outgoing")
    min_count = rule.get("min_count", 1)

    tinfo = ENTITY_TABLE_MAP.get(etype)
    einfo = EDGE_TABLE_MAP.get(rel_type)
    if not tinfo or not einfo:
        return []

    # Get all entities of this type
    entities = {}
    with database.snapshot() as snap:
        for r in snap.execute_sql(
            f"SELECT {tinfo['id_col']}, {tinfo['name_col']} FROM {tinfo['table']} WHERE {tenant_sql_filter_for(database, tinfo['table'])}",
            params=tp, param_types=tt,
        ):
            entities[r[0]] = r[1] or r[0]

    # Count edges per entity
    col = "source_id" if direction == "outgoing" else "target_id"
    type_col = "source_type" if direction == "outgoing" else "target_type"
    edge_counts = Counter()
    with database.snapshot() as snap:
        for r in snap.execute_sql(
            f"SELECT {col} FROM {einfo['table']} WHERE {type_col} = @etype AND {tenant_sql_filter_for(database, einfo['table'])}",
            params={"etype": etype, **tp}, param_types={"etype": _string_param_type(), **tt},
        ):
            if r[0] in entities:
                edge_counts[r[0]] += 1

    violations = []
    for eid, name in entities.items():
        if edge_counts.get(eid, 0) < min_count:
            violations.append(f"{name} ({etype}) has {edge_counts.get(eid, 0)} {rel_type} edges (min: {min_count})")
    return violations


def _check_forbidden_edge(database, rule: dict, tp: dict, tt: dict) -> list[str]:
    """Check that no edges exist between forbidden source/target type pairs."""
    rel_type = rule["relationship_type"]
    src_type = rule["source_type"]
    tgt_type = rule["target_type"]
    einfo = EDGE_TABLE_MAP.get(rel_type)
    if not einfo:
        return []

    violations = []
    with database.snapshot() as snap:
        rows = snap.execute_sql(
            f"SELECT source_id, target_id FROM {einfo['table']} "
            f"WHERE source_type = @st AND target_type = @tt AND {tenant_sql_filter_for(database, einfo['table'])}",
            params={"st": src_type, "tt": tgt_type, **tp},
            param_types={"st": _string_param_type(), "tt": _string_param_type(), **tt},
        )
        for r in rows:
            violations.append(f"Forbidden {src_type}->{tgt_type} via {rel_type} (src={r[0][:8]}..., tgt={r[1][:8]}...)")
    return violations


def _check_orphans(database, tp: dict, tt: dict) -> list[str]:
    """Find entities with zero connections in any edge table."""
    # Collect all entity IDs referenced in edges
    connected_ids = set()
    for _, einfo in EDGE_TABLE_MAP.items():
        try:
            with database.snapshot() as snap:
                for r in snap.execute_sql(
                    f"SELECT source_id FROM {einfo['table']} WHERE {tenant_sql_filter_for(database, einfo['table'])}",
                    params=tp, param_types=tt,
                ):
                    connected_ids.add(r[0])
            with database.snapshot() as snap:
                for r in snap.execute_sql(
                    f"SELECT target_id FROM {einfo['table']} WHERE {tenant_sql_filter_for(database, einfo['table'])}",
                    params=tp, param_types=tt,
                ):
                    connected_ids.add(r[0])
        except Exception:
            pass

    # Check each entity table
    violations = []
    for etype, tinfo in ENTITY_TABLE_MAP.items():
        try:
            with database.snapshot() as snap:
                for r in snap.execute_sql(
                    f"SELECT {tinfo['id_col']}, {tinfo['name_col']} FROM {tinfo['table']} WHERE {tenant_sql_filter_for(database, tinfo['table'])}",
                    params=tp, param_types=tt,
                ):
                    if r[0] not in connected_ids:
                        violations.append(f"{r[1] or r[0]} ({etype}) is an orphan")
        except Exception:
            pass
    return violations


def _check_ambiguous_only(database, tp: dict, tt: dict) -> list[str]:
    """Find entities where ALL connected edges are AMBIGUOUS."""
    # Collect entity->confidence info
    entity_confidences: dict[str, set] = {}
    for _, einfo in EDGE_TABLE_MAP.items():
        try:
            with database.snapshot() as snap:
                for r in snap.execute_sql(
                    f"SELECT source_id, confidence FROM {einfo['table']} WHERE {tenant_sql_filter_for(database, einfo['table'])}",
                    params=tp, param_types=tt,
                ):
                    entity_confidences.setdefault(r[0], set()).add(r[1] or "EXTRACTED")
            with database.snapshot() as snap:
                for r in snap.execute_sql(
                    f"SELECT target_id, confidence FROM {einfo['table']} WHERE {tenant_sql_filter_for(database, einfo['table'])}",
                    params=tp, param_types=tt,
                ):
                    entity_confidences.setdefault(r[0], set()).add(r[1] or "EXTRACTED")
        except Exception:
            pass

    violations = []
    for eid, confs in entity_confidences.items():
        if confs == {"AMBIGUOUS"}:
            violations.append(f"Entity {eid[:8]}... has only AMBIGUOUS connections")
    return violations


def _check_high_fan_in(database, rule: dict, tp: dict, tt: dict) -> list[str]:
    """Check entities with incoming edge count above threshold."""
    etype = rule["entity_type"]
    rel_type = rule["relationship_type"]
    threshold = rule.get("threshold", 3)

    tinfo = ENTITY_TABLE_MAP.get(etype)
    einfo = EDGE_TABLE_MAP.get(rel_type)
    if not tinfo or not einfo:
        return []

    # Count incoming edges per target entity of this type
    fan_in = Counter()
    with database.snapshot() as snap:
        for r in snap.execute_sql(
            f"SELECT target_id FROM {einfo['table']} WHERE target_type = @tt AND {tenant_sql_filter_for(database, einfo['table'])}",
            params={"tt": etype, **tp}, param_types={"tt": _string_param_type(), **tt},
        ):
            fan_in[r[0]] += 1

    # Resolve names for violations
    violations = []
    for eid, count in fan_in.items():
        if count > threshold:
            name = eid[:8]
            try:
                with database.snapshot() as snap:
                    for r in snap.execute_sql(
                        f"SELECT {tinfo['name_col']} FROM {tinfo['table']} WHERE {tinfo['id_col']} = @eid AND {tenant_sql_filter_for(database, tinfo['table'])}",
                        params={"eid": eid, **tp}, param_types={"eid": _string_param_type(), **tt},
                    ):
                        name = r[0] or eid[:8]
                        break
            except Exception:
                pass
            violations.append(f"{name} ({etype}) has {count} incoming {rel_type} edges (threshold: {threshold})")
    return violations


def _check_min_entities_per_doc(database, rule: dict, tp: dict, tt: dict) -> list[str]:
    """Check that each document produced at least min_count entities."""
    min_count = rule.get("min_count", 5)
    violations = []

    doc_entity_counts = Counter()
    doc_names = {}

    # Count entities per source_doc_id across all entity tables
    for etype, tinfo in ENTITY_TABLE_MAP.items():
        try:
            with database.snapshot() as snap:
                for r in snap.execute_sql(
                    f"SELECT source_doc_id FROM {tinfo['table']} WHERE source_doc_id IS NOT NULL AND {tenant_sql_filter_for(database, tinfo['table'])}",
                    params=tp, param_types=tt,
                ):
                    if r[0]:
                        doc_entity_counts[r[0]] += 1
        except Exception:
            pass

    # Get doc titles
    try:
        with database.snapshot() as snap:
            for r in snap.execute_sql(
                f"SELECT doc_id, title FROM Documents WHERE {tenant_sql_filter_for(database, 'Documents')}",
                params=tp, param_types=tt,
            ):
                doc_names[r[0]] = r[1] or r[0]
    except Exception:
        pass

    for doc_id, title in doc_names.items():
        count = doc_entity_counts.get(doc_id, 0)
        if count < min_count:
            violations.append(f"'{title}' produced only {count} entities (min: {min_count})")
    return violations


def _check_layer_coverage(database, rule: dict, tp: dict, tt: dict) -> list[str]:
    """Check that all required ArchiMate layers have at least one entity."""
    required = set(rule.get("required_layers", []))
    present = set()

    for etype, tinfo in ENTITY_TABLE_MAP.items():
        layer = ARCHIMATE_LAYER_MAP.get(etype, "")
        if layer in required:
            try:
                with database.snapshot() as snap:
                    for r in snap.execute_sql(
                        f"SELECT COUNT(*) FROM {tinfo['table']} WHERE {tenant_sql_filter_for(database, tinfo['table'])}",
                        params=tp, param_types=tt,
                    ):
                        if r[0] > 0:
                            present.add(layer)
            except Exception:
                pass

    missing = required - present
    if missing:
        return [f"Missing ArchiMate layer: {layer}" for layer in sorted(missing)]
    return []


# ---------------------------------------------------------------------------
# Impact Analysis
# ---------------------------------------------------------------------------

_CONFIDENCE_FACTOR = {"EXTRACTED": 1.0, "INFERRED": 0.5, "AMBIGUOUS": 0.0}


def impact_analysis(database, entity_name: str, entity_type: str, max_hops: int = 4, tenant_id: str | None = None) -> dict:
    """Calculate blast radius from an entity through all relationship layers.

    Uses BFS with confidence decay: EXTRACTED=1.0, INFERRED=0.5, AMBIGUOUS=0.0.
    NULL confidence treated as EXTRACTED (backward compat).
    """
    tp, tt = _tenant_params(tenant_id)
    # 1. Find source entity
    tinfo = ENTITY_TABLE_MAP.get(entity_type)
    if not tinfo:
        return {"error": f"Unknown entity type: {entity_type}"}

    source_id = None
    with database.snapshot() as snap:
        rows = snap.execute_sql(
            f"SELECT {tinfo['id_col']} FROM {tinfo['table']} WHERE LOWER({tinfo['name_col']}) = LOWER(@name) AND {tenant_sql_filter_for(database, tinfo['table'])} LIMIT 1",
            params={"name": entity_name, **tp}, param_types={"name": _string_param_type(), **tt},
        )
        for r in rows:
            source_id = r[0]

    if not source_id:
        return {"error": f"Entity not found: {entity_type}:{entity_name}"}

    # 2. BFS with confidence decay
    visited: dict[str, dict] = {}  # entity_id -> {type, hops, confidence, path}
    queue = deque()

    # Seed with source
    visited[source_id] = {"type": entity_type, "hops": 0, "confidence": 1.0, "path": entity_name}
    queue.append((source_id, entity_type, 0, 1.0, entity_name))

    while queue:
        eid, etype, hops, conf, path = queue.popleft()
        if hops >= max_hops:
            continue

        # Explore all edge tables in both directions
        neighbors = _get_neighbors_all_tables(database, eid, etype, tp, tt)

        for neighbor_id, neighbor_type, rel_type, edge_conf, direction in neighbors:
            factor = _CONFIDENCE_FACTOR.get(edge_conf or "EXTRACTED", 1.0)
            new_conf = conf * factor
            if new_conf < 0.1:
                continue  # Prune low-confidence paths

            new_hops = hops + 1
            arrow = f" -[{rel_type}, {edge_conf or 'EXTRACTED'}]-> " if direction == "outgoing" else f" <-[{rel_type}, {edge_conf or 'EXTRACTED'}]- "
            new_path = path + arrow + f"({neighbor_type})"

            # Keep only highest-confidence path per entity
            if neighbor_id not in visited or visited[neighbor_id]["confidence"] < new_conf:
                visited[neighbor_id] = {
                    "type": neighbor_type,
                    "hops": new_hops,
                    "confidence": new_conf,
                    "path": new_path,
                }
                queue.append((neighbor_id, neighbor_type, new_hops, new_conf, new_path))

    # 3. Batch resolve names
    del visited[source_id]  # Remove source from results
    _resolve_names_batch(database, visited, tp, tt)

    # 4. Build result
    impacted = []
    layer_summary = Counter()
    for eid, info in visited.items():
        layer = ARCHIMATE_LAYER_MAP.get(info["type"], "Other")
        layer_summary[layer] += 1
        impacted.append({
            "entity_id": eid,
            "name": info.get("name", eid[:12]),
            "type": info["type"],
            "layer": layer,
            "hops": info["hops"],
            "confidence": round(info["confidence"], 3),
            "path": info["path"],
        })

    impacted.sort(key=lambda x: (x["hops"], -x["confidence"]))
    total = len(impacted)
    weighted = round(sum(e["confidence"] for e in impacted), 1)
    max_hop = max((e["hops"] for e in impacted), default=0)

    return {
        "source": {"name": entity_name, "type": entity_type, "entity_id": source_id},
        "impacted_entities": impacted[:50],  # Cap output
        "layer_summary": dict(layer_summary),
        "total_blast_radius": total,
        "confidence_weighted_radius": weighted,
        "max_hops_reached": max_hop,
    }


def _get_neighbors_all_tables(database, entity_id: str, entity_type: str, tp: dict, tt: dict) -> list[tuple]:
    """Get all neighbors of an entity across all edge tables.

    Returns: [(neighbor_id, neighbor_type, rel_type, confidence, direction), ...]
    """
    neighbors = []
    for rel_type, einfo in EDGE_TABLE_MAP.items():
        try:
            # Outgoing: entity is source
            with database.snapshot() as snap:
                rows = snap.execute_sql(
                    f"SELECT target_id, target_type, confidence FROM {einfo['table']} WHERE source_id = @eid AND {tenant_sql_filter_for(database, einfo['table'])}",
                    params={"eid": entity_id, **tp}, param_types={"eid": _string_param_type(), **tt},
                )
                for r in rows:
                    if r[0]:
                        neighbors.append((r[0], r[1] or "", rel_type, r[2], "outgoing"))
            # Incoming: entity is target
            with database.snapshot() as snap:
                rows = snap.execute_sql(
                    f"SELECT source_id, source_type, confidence FROM {einfo['table']} WHERE target_id = @eid AND {tenant_sql_filter_for(database, einfo['table'])}",
                    params={"eid": entity_id, **tp}, param_types={"eid": _string_param_type(), **tt},
                )
                for r in rows:
                    if r[0]:
                        neighbors.append((r[0], r[1] or "", rel_type, r[2], "incoming"))
        except Exception:
            pass
    return neighbors


def _resolve_names_batch(database, visited: dict, tp: dict, tt: dict):
    """Resolve entity names in batch, grouped by type."""
    by_type: dict[str, list[str]] = {}
    for eid, info in visited.items():
        by_type.setdefault(info["type"], []).append(eid)

    for etype, ids in by_type.items():
        tinfo = ENTITY_TABLE_MAP.get(etype)
        if not tinfo:
            continue
        # Query in batches of 50
        for i in range(0, len(ids), 50):
            batch = ids[i:i+50]
            params = {f"id{j}": eid for j, eid in enumerate(batch)}
            params.update(tp)
            ptypes = {f"id{j}": _string_param_type() for j in range(len(batch))}
            ptypes.update(tt)
            where = " OR ".join(f"{tinfo['id_col']} = @id{j}" for j in range(len(batch)))
            try:
                with database.snapshot() as snap:
                    rows = snap.execute_sql(
                        f"SELECT {tinfo['id_col']}, {tinfo['name_col']} FROM {tinfo['table']} WHERE ({where}) AND {tenant_sql_filter_for(database, tinfo['table'])}",
                        params=params, param_types=ptypes,
                    )
                    for r in rows:
                        if r[0] in visited and r[1]:
                            visited[r[0]]["name"] = r[1]
            except Exception:
                pass
