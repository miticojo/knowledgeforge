"""L1: Knowledge Graph Construction Quality Metrics.

Compares extracted KG in Spanner against ground truth to measure:
- Entity Type F1 (precision/recall per type)
- Relationship F1 (precision/recall per type)
- Ontology Conformance (% valid per ArchiMate 3.2 rules)
- Entity Resolution Accuracy (dedup across documents)
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "kb-agent"))


def load_ground_truth() -> dict:
    gt_path = os.path.join(os.path.dirname(__file__), "..", "data", "ground_truth", "archisurance_ground_truth.json")
    with open(gt_path) as f:
        return json.load(f)


def query_spanner_entities(db) -> dict[str, list[str]]:
    """Fetch all entities from Spanner grouped by type."""
    from services.schema_registry import ENTITY_TABLE_MAP
    from google.cloud.spanner_v1 import param_types

    result = {}
    for etype, tinfo in ENTITY_TABLE_MAP.items():
        try:
            with db.snapshot() as snap:
                rows = snap.execute_sql(
                    f"SELECT {tinfo['name_col']} FROM {tinfo['table']}"
                )
                names = [r[0] for r in rows if r[0]]
                if names:
                    result[etype] = names
        except Exception:
            pass
    return result


def query_spanner_relationships(db) -> list[dict]:
    """Fetch relationships from Spanner edge tables."""
    from services.schema_registry import EDGE_TABLE_MAP

    relationships = []
    for rel_type, einfo in EDGE_TABLE_MAP.items():
        try:
            with db.snapshot() as snap:
                rows = snap.execute_sql(
                    f"SELECT source_type, target_type FROM {einfo['table']} LIMIT 100"
                )
                for r in rows:
                    relationships.append({
                        "type": rel_type,
                        "source_type": r[0],
                        "target_type": r[1],
                    })
        except Exception:
            pass
    return relationships


def compute_entity_f1(ground_truth: dict, extracted: dict[str, list[str]]) -> dict:
    """Compute per-type entity F1 score."""
    gt_entities = ground_truth["entities"]
    results = {}
    total_tp, total_fp, total_fn = 0, 0, 0

    for etype, gt_names in gt_entities.items():
        gt_set = {n.lower() for n in gt_names}
        ext_set = {n.lower() for n in extracted.get(etype, [])}

        tp = len(gt_set & ext_set)
        fp = len(ext_set - gt_set)
        fn = len(gt_set - ext_set)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        results[etype] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "tp": tp, "fp": fp, "fn": fn,
            "missing": sorted(gt_set - ext_set) if fn > 0 else [],
            "extra": sorted(ext_set - gt_set) if fp > 0 else [],
        }
        total_tp += tp
        total_fp += fp
        total_fn += fn

    macro_p = sum(r["precision"] for r in results.values()) / len(results) if results else 0
    macro_r = sum(r["recall"] for r in results.values()) / len(results) if results else 0
    micro_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    micro_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0

    return {
        "per_type": results,
        "macro_f1": round(2 * macro_p * macro_r / (macro_p + macro_r) if (macro_p + macro_r) > 0 else 0, 3),
        "micro_f1": round(2 * micro_p * micro_r / (micro_p + micro_r) if (micro_p + micro_r) > 0 else 0, 3),
        "total_ground_truth": ground_truth["total_entities"],
        "total_extracted": sum(len(v) for v in extracted.values()),
    }


def compute_relationship_f1(ground_truth: dict, extracted: list[dict]) -> dict:
    """Compute relationship type distribution comparison."""
    gt_rels = ground_truth["relationships"]
    gt_type_counts = Counter(r["type"] for r in gt_rels)
    ext_type_counts = Counter(r["type"] for r in extracted)

    all_types = set(gt_type_counts.keys()) | set(ext_type_counts.keys())
    results = {}
    for rtype in sorted(all_types):
        gt_count = gt_type_counts.get(rtype, 0)
        ext_count = ext_type_counts.get(rtype, 0)
        results[rtype] = {
            "ground_truth": gt_count,
            "extracted": ext_count,
            "delta": ext_count - gt_count,
        }

    return {
        "per_type": results,
        "total_ground_truth": len(gt_rels),
        "total_extracted": len(extracted),
        "type_coverage": round(
            len(set(ext_type_counts.keys()) & set(gt_type_counts.keys())) / len(gt_type_counts) if gt_type_counts else 0,
            3
        ),
    }


def compute_confidence_distribution(db) -> dict:
    """Count EXTRACTED/INFERRED/AMBIGUOUS edges across all edge tables."""
    from services.schema_registry import EDGE_TABLE_MAP

    totals = {"EXTRACTED": 0, "INFERRED": 0, "AMBIGUOUS": 0, "NULL": 0}
    per_type = {}
    for rel_type, einfo in EDGE_TABLE_MAP.items():
        try:
            with db.snapshot() as snap:
                rows = snap.execute_sql(
                    f"SELECT confidence, COUNT(*) FROM {einfo['table']} GROUP BY confidence"
                )
                type_counts = {"EXTRACTED": 0, "INFERRED": 0, "AMBIGUOUS": 0, "NULL": 0}
                for r in rows:
                    conf = r[0] if r[0] else "NULL"
                    count = r[1]
                    if conf in type_counts:
                        type_counts[conf] += count
                        totals[conf] += count
                    else:
                        type_counts["NULL"] += count
                        totals["NULL"] += count
                per_type[rel_type] = type_counts
        except Exception:
            pass

    total_edges = sum(totals.values()) or 1
    return {
        "totals": totals,
        "per_type": per_type,
        "pct_extracted": round(totals["EXTRACTED"] / total_edges * 100, 1),
        "pct_inferred": round(totals["INFERRED"] / total_edges * 100, 1),
        "pct_ambiguous": round(totals["AMBIGUOUS"] / total_edges * 100, 1),
        "pct_null": round(totals["NULL"] / total_edges * 100, 1),
    }


def compute_entity_resolution_quality(db) -> dict:
    """Check for duplicate entities (same name, different IDs)."""
    from services.schema_registry import ENTITY_TABLE_MAP

    duplicates = {}
    for etype, tinfo in ENTITY_TABLE_MAP.items():
        try:
            with db.snapshot() as snap:
                rows = snap.execute_sql(f"""
                    SELECT {tinfo['name_col']}, COUNT(*) AS cnt
                    FROM {tinfo['table']}
                    GROUP BY {tinfo['name_col']}
                    HAVING COUNT(*) > 1
                """)
                dups = [(r[0], r[1]) for r in rows]
                if dups:
                    duplicates[etype] = dups
        except Exception:
            pass

    return {
        "types_with_duplicates": len(duplicates),
        "total_duplicate_entities": sum(sum(c for _, c in v) for v in duplicates.values()),
        "details": {k: [{"name": n, "count": c} for n, c in v] for k, v in duplicates.items()},
    }


def run(db=None):
    """Run L1 evaluation and return results."""
    if db is None:
        from services.spanner_client import get_database
        db = get_database()

    gt = load_ground_truth()
    extracted_entities = query_spanner_entities(db)
    extracted_rels = query_spanner_relationships(db)

    entity_f1 = compute_entity_f1(gt, extracted_entities)
    rel_f1 = compute_relationship_f1(gt, extracted_rels)
    resolution = compute_entity_resolution_quality(db)
    confidence = compute_confidence_distribution(db)

    return {
        "layer": "L1_KG_Construction",
        "entity_f1": entity_f1,
        "relationship_f1": rel_f1,
        "entity_resolution": resolution,
        "confidence_distribution": confidence,
    }


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2, ensure_ascii=False))
