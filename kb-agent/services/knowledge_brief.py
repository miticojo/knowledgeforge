"""Knowledge Brief generator: structured context for AI agent consumption.

Produces a markdown document summarizing the knowledge graph state —
core entities, relationship patterns, high-confidence chains, gaps,
and source documents — so an AI agent can orient itself before working.
"""
import logging
from services.graph_analytics import get_god_nodes, get_graph_stats
from services.schema_registry import EDGE_TABLE_MAP, ENTITY_TABLE_MAP, ARCHIMATE_LAYER_MAP
from services.tenant_context import get_tenant, SHARED_TENANT

logger = logging.getLogger(__name__)

_TENANT_FILTER = f"tenant_id IN (@_tid, '{SHARED_TENANT}')"


def generate_brief(database, god_nodes_limit: int = 15, tenant_id: str | None = None) -> str:
    """Generate a structured knowledge brief for AI agent consumption."""
    _tid = tenant_id if tenant_id is not None else get_tenant()
    stats = get_graph_stats(database, tenant_id=_tid)
    god_nodes = get_god_nodes(database, top_n=god_nodes_limit, tenant_id=_tid)

    lines = ["# Knowledge Base Brief", ""]

    # --- Graph Overview ---
    lines.append("## Graph Overview")
    conf = stats.get("confidence_distribution", {})
    total_conf = sum(conf.values()) or 1
    lines.append(f"- {stats['total_entities']} entities across {len(stats.get('entities_by_type', {}))} ArchiMate types")
    lines.append(f"- {stats['total_edges']} relationships ({_pct(conf.get('EXTRACTED', 0), total_conf)}% EXTRACTED, "
                 f"{_pct(conf.get('INFERRED', 0), total_conf)}% INFERRED, "
                 f"{_pct(conf.get('AMBIGUOUS', 0), total_conf)}% AMBIGUOUS)")
    lines.append(f"- {stats.get('documents', 0)} source documents, {stats.get('chunks', 0)} chunks")
    lines.append("")

    # --- Core Entities ---
    lines.append("## Core Entities (highest connectivity)")
    for i, node in enumerate(god_nodes, 1):
        lines.append(f"{i}. **{node['name']}** ({node['type']}) — {node['degree']} connections")
    lines.append("")

    # --- Entity Type Distribution ---
    lines.append("## Entity Distribution by Type")
    eby = stats.get("entities_by_type", {})
    for etype, count in sorted(eby.items(), key=lambda x: -x[1]):
        layer = ARCHIMATE_LAYER_MAP.get(etype, "")
        lines.append(f"- {etype} [{layer}]: {count}")
    lines.append("")

    # --- Relationship Distribution ---
    lines.append("## Relationship Distribution")
    rby = stats.get("edges_by_type", {})
    for rtype, count in sorted(rby.items(), key=lambda x: -x[1]):
        lines.append(f"- {rtype}: {count}")
    lines.append("")

    # --- High-Confidence Connections (from god nodes) ---
    lines.append("## Key Connections (from top entities)")
    _connections = _get_god_node_connections(database, god_nodes[:5], _tid)
    for conn in _connections[:20]:
        lines.append(f"- {conn}")
    lines.append("")

    # --- Knowledge Gaps ---
    lines.append("## Knowledge Gaps")
    gaps = _identify_gaps(stats, god_nodes)
    for gap in gaps:
        lines.append(f"- {gap}")
    if not gaps:
        lines.append("- No significant gaps detected")
    lines.append("")

    # --- Conformance Report ---
    try:
        from services.graph_analytics import check_conformance
        conf_report = check_conformance(database, tenant_id=_tid)
        lines.append("## Conformance Report")
        lines.append(f"Summary: {conf_report['passed']}/{conf_report['total_rules']} passed, "
                     f"{conf_report['warnings']} warnings, {conf_report['errors']} errors")
        for r in conf_report.get("results", []):
            icon = "PASS" if r["status"] == "passed" else r["severity"].upper()
            count = f" ({r['violation_count']} violations)" if r["status"] != "passed" else ""
            lines.append(f"- {r['rule_id']} [{icon}] {r['description']}{count}")
        lines.append("")
    except Exception as e:
        lines.append("## Conformance Report")
        lines.append(f"- Could not run conformance check: {e}")
        lines.append("")

    # --- Source Documents ---
    lines.append("## Source Documents")
    docs = _get_document_summary(database, _tid)
    if docs:
        lines.append("| Title | Date | Entities Mentioned |")
        lines.append("|-------|------|-------------------|")
        for doc in docs:
            lines.append(f"| {doc['title']} | {doc['date']} | {doc['mentions']} |")
    lines.append("")

    return "\n".join(lines)


def _pct(value: int, total: int) -> str:
    return str(round(value / total * 100)) if total > 0 else "0"


def _get_god_node_connections(database, god_nodes: list[dict], tenant_id: str) -> list[str]:
    """Get direct connections for top god nodes."""
    connections = []
    for node in god_nodes:
        etype = node.get("type", "")
        tinfo = ENTITY_TABLE_MAP.get(etype)
        if not tinfo:
            continue
        for rel_type, einfo in EDGE_TABLE_MAP.items():
            try:
                with database.snapshot() as snap:
                    rows = snap.execute_sql(
                        f"SELECT target_type, confidence FROM {einfo['table']} "
                        f"WHERE source_id = @eid AND {_TENANT_FILTER} LIMIT 3",
                        params={"eid": node["entity_id"], "_tid": tenant_id},
                        param_types={"eid": _string_param_type(), "_tid": _string_param_type()},
                    )
                    for r in rows:
                        conf = r[1] if r[1] else "EXTRACTED"
                        connections.append(f"{node['name']} ({etype}) -[{rel_type}, {conf}]-> ({r[0]})")
            except Exception:
                pass
    return connections


def _identify_gaps(stats: dict, god_nodes: list[dict]) -> list[str]:
    """Identify knowledge gaps from graph statistics."""
    gaps = []
    conf = stats.get("confidence_distribution", {})
    total = sum(conf.values()) or 1

    ambiguous_pct = conf.get("AMBIGUOUS", 0) / total * 100
    if ambiguous_pct > 5:
        gaps.append(f"{round(ambiguous_pct)}% of edges are AMBIGUOUS — review recommended")

    null_pct = conf.get("NULL", 0) / total * 100
    if null_pct > 10:
        gaps.append(f"{round(null_pct)}% of edges have no confidence label (pre-migration data)")

    # Check for entity types with zero entries
    eby = stats.get("entities_by_type", {})
    all_types = set(ENTITY_TABLE_MAP.keys())
    missing = all_types - set(eby.keys())
    if missing:
        gaps.append(f"No entities found for types: {', '.join(sorted(missing))}")

    # Check for relationship types with zero edges
    rby = stats.get("edges_by_type", {})
    all_rels = set(EDGE_TABLE_MAP.keys())
    missing_rels = all_rels - set(rby.keys())
    if missing_rels:
        gaps.append(f"No edges found for relationship types: {', '.join(sorted(missing_rels))}")

    return gaps


def _get_document_summary(database, tenant_id: str) -> list[dict]:
    """Get a summary of all documents with mention counts."""
    docs = []
    _tp = {"_tid": tenant_id}
    _tt = {"_tid": _string_param_type()}
    try:
        with database.snapshot() as snap:
            rows = snap.execute_sql(
                f"SELECT d.doc_id, d.title, d.document_date, "
                f"(SELECT COUNT(*) FROM DocumentMentions dm WHERE dm.doc_id = d.doc_id AND dm.{_TENANT_FILTER}) AS mentions "
                f"FROM Documents d WHERE d.{_TENANT_FILTER} ORDER BY d.title",
                params=_tp, param_types=_tt,
            )
            for r in rows:
                docs.append({
                    "doc_id": r[0],
                    "title": r[1] or "Untitled",
                    "date": r[2] or "",
                    "mentions": r[3] or 0,
                })
    except Exception as e:
        logger.debug(f"Document summary query failed: {e}")
        # Fallback: simple query without subquery
        try:
            with database.snapshot() as snap:
                rows = snap.execute_sql(
                    f"SELECT doc_id, title, document_date FROM Documents WHERE {_TENANT_FILTER} ORDER BY title",
                    params=_tp, param_types=_tt,
                )
                for r in rows:
                    docs.append({
                        "doc_id": r[0],
                        "title": r[1] or "Untitled",
                        "date": r[2] or "",
                        "mentions": "N/A",
                    })
        except Exception:
            pass
    return docs


def _string_param_type():
    from google.cloud.spanner_v1 import param_types
    return param_types.STRING
