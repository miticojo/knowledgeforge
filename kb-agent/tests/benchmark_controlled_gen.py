"""
Benchmark: Controlled Generation vs Free-Form Extraction for ArchiMate Graph Extraction

Compares two approaches:
  A) Free-form text extraction → regex normalization (current production approach)
  B) Controlled Generation with response_schema → zero parsing needed

Uses 4 E2E scenarios from test_e2e_extraction_scenarios.py as ground truth.
Runs 3 iterations per scenario for statistical stability.
"""
import os
import sys
import json
import time
import statistics
from typing import Literal, Optional
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from google import genai
from google.genai import types as genai_types

from agents.processing import (
    _normalize_node,
    _classify_relationship,
    VALID_ENTITY_TYPES,
    VALID_RELATIONSHIP_TYPES,
)
from tests.test_e2e_extraction_scenarios import ALL_SCENARIOS
from tests.test_graph_extraction import parse_node, parse_edge

# ---------------------------------------------------------------------------
# Pydantic schema for Controlled Generation (Approach B)
# ---------------------------------------------------------------------------

ENTITY_TYPES = Literal[
    "ApplicationComponent", "DataObject", "BusinessProcess", "Requirement",
    "Node", "SystemSoftware", "TechnologyService", "BusinessActor",
    "BusinessRole", "BusinessService", "BusinessFunction", "BusinessObject",
    "ApplicationService", "ApplicationInterface", "Artifact", "Device",
    "CommunicationNetwork", "Contract", "Goal", "Constraint", "Stakeholder",
    "Capability",
]

RELATIONSHIP_TYPES = Literal[
    "Composition", "Aggregation", "Assignment", "Realization", "Serving",
    "Access", "Influence", "Association", "Triggering", "Flow", "Specialization",
]


class ExtractedNode(BaseModel):
    entity_type: ENTITY_TYPES
    entity_name: str


class ExtractedEdge(BaseModel):
    source_type: ENTITY_TYPES
    source_name: str
    relationship_type: RELATIONSHIP_TYPES
    target_type: ENTITY_TYPES
    target_name: str
    qualifier: Optional[str] = None


class GraphExtraction(BaseModel):
    nodes: list[ExtractedNode]
    edges: list[ExtractedEdge]


# ---------------------------------------------------------------------------
# Shared extraction prompt (from ProcessingAgent instruction, graph part only)
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You are a Knowledge Graph extraction agent. Read the document below
and extract ALL entities and relationships following the ArchiMate 3.2 Wave 2 ontology.

=== ALLOWED ENTITY TYPES (22 types) ===

STRATEGY: Capability
BUSINESS: BusinessActor, BusinessRole, BusinessProcess, BusinessFunction, BusinessService, BusinessObject, Contract
APPLICATION: ApplicationComponent, ApplicationService, ApplicationInterface, DataObject
TECHNOLOGY: Node, Device, SystemSoftware, TechnologyService, Artifact, CommunicationNetwork
MOTIVATION: Goal, Requirement, Constraint, Stakeholder

=== RELATIONSHIP TYPES (11 types) ===

STRUCTURAL: Composition, Aggregation, Assignment, Realization
DEPENDENCY: Serving, Access, Influence, Association
DYNAMIC: Triggering, Flow
OTHER: Specialization

=== CLASSIFICATION DECISION TREE ===

1. Person/team/department/organization? -> BusinessActor
2. Named responsibility (no physical entity)? -> BusinessRole
3. Software, application, system, platform? -> ApplicationComponent
4. API, endpoint, access point? -> ApplicationInterface
5. Service exposed by an application? -> ApplicationService
6. OS, middleware, DBMS, runtime, container engine? -> SystemSoftware
7. Server, VM, HW+SW platform? -> Node
8. Physical hardware (router, firewall, switch)? -> Device
9. Network (LAN, WAN, VPN)? -> CommunicationNetwork
10. Deployable file, script, executable? -> Artifact
11. Structured data for applications? -> DataObject
12. Business information concept? -> BusinessObject
13. Operational workflow/procedure? -> BusinessProcess
14. Competency grouping? -> BusinessFunction
15. Exposed business service? -> BusinessService
16. Formal agreement/SLA? -> Contract
17. Strategic objective? -> Goal
18. Functional/non-functional requirement? -> Requirement
19. Limitation/constraint? -> Constraint
20. Role with architecture interests? -> Stakeholder
21. Organizational/system capability? -> Capability
22. Exposed infrastructure service? -> TechnologyService

=== DIRECTION RULES ===

- Assignment: Active Structure -> Behavior
- Realization: Concrete -> Abstract
- Serving: Provider -> Consumer
- Access: Behavior -> Data (qualifier: Read, Write, ReadWrite)
- Composition/Aggregation: Whole -> Part
- Specialization: Specific -> Generic
- Influence: any -> Motivation element (qualifier: +, -, ++, --)
- Triggering/Flow: Source -> Destination

DOCUMENT:
{document_text}

Extract ALL entities and relationships from this document."""

# Free-form specific suffix
FREEFORM_SUFFIX = """

Output format:
NODES (one per line, format "EntityType:EntityName"):
[list all nodes]

EDGES (one per line, format "SourceType:SourceName->RelationType->TargetType:TargetName"):
[list all edges]"""


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------

def extract_freeform(client: genai.Client, document_text: str) -> tuple[dict, float]:
    """Approach A: Free-form text extraction + normalization."""
    prompt = EXTRACTION_PROMPT.format(document_text=document_text) + FREEFORM_SUFFIX

    start = time.time()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.0,
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        ),
    )
    latency_ms = (time.time() - start) * 1000

    text = response.text
    raw_nodes = []
    raw_edges = []
    parsing_errors = 0

    # Parse NODES section
    in_nodes = False
    in_edges = False
    for line in text.split("\n"):
        line = line.strip().lstrip("- ").lstrip("* ").lstrip("0123456789. ")
        if not line:
            continue
        if "NODES" in line.upper() or "NODI" in line.upper():
            in_nodes = True
            in_edges = False
            continue
        if "EDGES" in line.upper() or "ARCHI" in line.upper():
            in_edges = True
            in_nodes = False
            continue

        if in_nodes and ":" in line:
            raw_nodes.append(line)
        elif in_edges and "->" in line:
            raw_edges.append(line)

    # Normalize nodes using production normalization
    normalized_nodes = []
    node_map = {}
    raw_to_key = {}
    for raw in raw_nodes:
        try:
            entity_type, name = _normalize_node(raw)
            key = f"{entity_type}:{name}"
            normalized_nodes.append(key)
            node_map[key] = name
            raw_to_key[raw] = key
            raw_to_key[name] = key
            # Check if normalization was needed
            if ":" in raw:
                candidate_type = raw.split(":", 1)[0].strip()
                if candidate_type not in VALID_ENTITY_TYPES:
                    parsing_errors += 1
            else:
                parsing_errors += 1  # No type prefix at all
        except Exception:
            parsing_errors += 1

    # Normalize edges
    normalized_edges = []
    for raw in raw_edges:
        try:
            parts = raw.split("->")
            if len(parts) < 3:
                parsing_errors += 1
                continue
            src_raw = parts[0].strip()
            verb = parts[1].strip()
            tgt_raw = "->".join(parts[2:]).strip()

            # Extract qualifier if present
            qualifier = None
            if "[" in verb:
                verb_clean = verb.split("[")[0]
                qualifier = verb.split("[")[1].rstrip("]")
            else:
                verb_clean = verb

            rel_type = _classify_relationship(verb_clean)
            src_key = raw_to_key.get(src_raw) or raw_to_key.get(
                src_raw.split(":", 1)[-1] if ":" in src_raw else src_raw
            )
            tgt_key = raw_to_key.get(tgt_raw) or raw_to_key.get(
                tgt_raw.split(":", 1)[-1] if ":" in tgt_raw else tgt_raw
            )

            if src_key and tgt_key:
                edge_str = f"{src_key}->{rel_type}"
                if qualifier:
                    edge_str += f"[{qualifier}]"
                edge_str += f"->{tgt_key}"
                normalized_edges.append(edge_str)
            else:
                parsing_errors += 1
        except Exception:
            parsing_errors += 1

    return {
        "nodes": normalized_nodes,
        "edges": normalized_edges,
        "raw_node_count": len(raw_nodes),
        "raw_edge_count": len(raw_edges),
        "parsing_errors": parsing_errors,
        "latency_ms": latency_ms,
    }, latency_ms


def extract_controlled(client: genai.Client, document_text: str) -> tuple[dict, float]:
    """Approach B: Controlled Generation with response_schema."""
    prompt = EXTRACTION_PROMPT.format(document_text=document_text)

    start = time.time()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=GraphExtraction,
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        ),
    )
    latency_ms = (time.time() - start) * 1000

    # Parse structured JSON response
    try:
        data = json.loads(response.text)
        extraction = GraphExtraction(**data)
    except Exception as e:
        print(f"  [CONTROLLED] JSON parse failed: {e}")
        print(f"  Response text: {response.text[:500]}")
        return {
            "nodes": [],
            "edges": [],
            "raw_node_count": 0,
            "raw_edge_count": 0,
            "parsing_errors": 1,
            "latency_ms": latency_ms,
            "schema_error": str(e),
        }, latency_ms

    # Convert to same format as freeform for comparison
    nodes = [f"{n.entity_type}:{n.entity_name}" for n in extraction.nodes]
    edges = []
    for e in extraction.edges:
        edge_str = f"{e.source_type}:{e.source_name}->{e.relationship_type}"
        if e.qualifier:
            edge_str += f"[{e.qualifier}]"
        edge_str += f"->{e.target_type}:{e.target_name}"
        edges.append(edge_str)

    # Check schema compliance (should be 100% with controlled gen)
    schema_violations = 0
    for n in extraction.nodes:
        if n.entity_type not in VALID_ENTITY_TYPES:
            schema_violations += 1
    for e in extraction.edges:
        if e.source_type not in VALID_ENTITY_TYPES:
            schema_violations += 1
        if e.target_type not in VALID_ENTITY_TYPES:
            schema_violations += 1
        if e.relationship_type not in VALID_RELATIONSHIP_TYPES:
            schema_violations += 1

    return {
        "nodes": nodes,
        "edges": edges,
        "raw_node_count": len(extraction.nodes),
        "raw_edge_count": len(extraction.edges),
        "parsing_errors": 0,  # By design — schema enforced
        "schema_violations": schema_violations,
        "latency_ms": latency_ms,
    }, latency_ms


# ---------------------------------------------------------------------------
# Comparison metrics
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Normalize entity name for fuzzy matching."""
    return name.lower().strip()


def compute_node_metrics(extracted: list[str], ground_truth: list[str]) -> dict:
    """Compute node-level metrics: type accuracy, name match, F1."""
    gt_types = {}  # name -> type
    for n in ground_truth:
        t, name = parse_node(n)
        gt_types[_normalize_name(name)] = t

    ext_types = {}
    for n in extracted:
        try:
            t, name = parse_node(n)
            ext_types[_normalize_name(name)] = t
        except ValueError:
            continue

    # Match by name (fuzzy: check if GT name is contained in extracted or vice versa)
    matched = 0
    type_correct = 0
    matched_gt_names = set()

    for ext_name, ext_type in ext_types.items():
        best_match = None
        for gt_name, gt_type in gt_types.items():
            if gt_name in ext_name or ext_name in gt_name:
                best_match = gt_name
                break
        if best_match:
            matched += 1
            matched_gt_names.add(best_match)
            if ext_type == gt_types[best_match]:
                type_correct += 1

    precision = matched / len(ext_types) if ext_types else 0
    recall = len(matched_gt_names) / len(gt_types) if gt_types else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        "extracted_count": len(ext_types),
        "gt_count": len(gt_types),
        "matched": matched,
        "type_correct": type_correct,
        "type_accuracy": type_correct / matched if matched > 0 else 0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def compute_edge_metrics(extracted: list[str], ground_truth: list[str]) -> dict:
    """Compute edge-level metrics: relationship type accuracy, F1."""
    gt_edges = []
    for e in ground_truth:
        try:
            edge = parse_edge(e)
            gt_edges.append(edge)
        except ValueError:
            continue

    ext_edges = []
    for e in extracted:
        try:
            edge = parse_edge(e)
            ext_edges.append(edge)
        except ValueError:
            continue

    # Match edges by source+target name (fuzzy)
    matched = 0
    rel_correct = 0
    matched_gt_indices = set()

    for ext_edge in ext_edges:
        ext_src = _normalize_name(ext_edge["source_name"])
        ext_tgt = _normalize_name(ext_edge["target_name"])
        best_idx = None
        for i, gt_edge in enumerate(gt_edges):
            if i in matched_gt_indices:
                continue
            gt_src = _normalize_name(gt_edge["source_name"])
            gt_tgt = _normalize_name(gt_edge["target_name"])
            if (gt_src in ext_src or ext_src in gt_src) and \
               (gt_tgt in ext_tgt or ext_tgt in gt_tgt):
                best_idx = i
                break
        if best_idx is not None:
            matched += 1
            matched_gt_indices.add(best_idx)
            if ext_edge["relationship_type"] == gt_edges[best_idx]["relationship_type"]:
                rel_correct += 1

    precision = matched / len(ext_edges) if ext_edges else 0
    recall = len(matched_gt_indices) / len(gt_edges) if gt_edges else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        "extracted_count": len(ext_edges),
        "gt_count": len(gt_edges),
        "matched": matched,
        "rel_correct": rel_correct,
        "rel_accuracy": rel_correct / matched if matched > 0 else 0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


# ---------------------------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------------------------

def run_benchmark(n_runs: int = 3):
    """Run the full benchmark: n_runs per scenario, both approaches."""
    client = genai.Client()

    print("=" * 80)
    print("BENCHMARK: Controlled Generation vs Free-Form for ArchiMate Graph Extraction")
    print(f"Model: gemini-2.5-flash | Runs per scenario: {n_runs}")
    print("=" * 80)

    all_results = {}

    for scenario in ALL_SCENARIOS:
        print(f"\n{'─' * 70}")
        print(f"Scenario: {scenario.name}")
        print(f"Ground truth: {len(scenario.expected_nodes)} nodes, {len(scenario.expected_edges)} edges")
        print(f"{'─' * 70}")

        freeform_runs = []
        controlled_runs = []

        for run in range(n_runs):
            print(f"\n  Run {run + 1}/{n_runs}...")

            # Approach A: Free-form
            print(f"    [A] Free-form extraction...", end=" ", flush=True)
            ff_result, ff_lat = extract_freeform(client, scenario.document_text)
            ff_nodes = compute_node_metrics(ff_result["nodes"], scenario.expected_nodes)
            ff_edges = compute_edge_metrics(ff_result["edges"], scenario.expected_edges)
            ff_result["node_metrics"] = ff_nodes
            ff_result["edge_metrics"] = ff_edges
            freeform_runs.append(ff_result)
            print(f"{ff_lat:.0f}ms | nodes F1={ff_nodes['f1']:.3f} | edges F1={ff_edges['f1']:.3f} | parse_err={ff_result['parsing_errors']}")

            # Approach B: Controlled Generation
            print(f"    [B] Controlled generation...", end=" ", flush=True)
            cg_result, cg_lat = extract_controlled(client, scenario.document_text)
            cg_nodes = compute_node_metrics(cg_result["nodes"], scenario.expected_nodes)
            cg_edges = compute_edge_metrics(cg_result["edges"], scenario.expected_edges)
            cg_result["node_metrics"] = cg_nodes
            cg_result["edge_metrics"] = cg_edges
            controlled_runs.append(cg_result)
            print(f"{cg_lat:.0f}ms | nodes F1={cg_nodes['f1']:.3f} | edges F1={cg_edges['f1']:.3f} | schema_viol={cg_result.get('schema_violations', 0)}")

        # Aggregate results
        all_results[scenario.name] = {
            "freeform": freeform_runs,
            "controlled": controlled_runs,
        }

    # ---------------------------------------------------------------------------
    # Summary table
    # ---------------------------------------------------------------------------
    print("\n\n" + "=" * 100)
    print("SUMMARY TABLE (averaged over {} runs)".format(n_runs))
    print("=" * 100)

    header = f"{'Scenario':<35} | {'Approach':<12} | {'Node F1':>8} | {'Edge F1':>8} | {'Type Acc':>8} | {'Rel Acc':>8} | {'Parse Err':>9} | {'Latency':>8}"
    print(header)
    print("─" * len(header))

    overall_ff = {"node_f1": [], "edge_f1": [], "type_acc": [], "rel_acc": [], "parse_err": [], "latency": []}
    overall_cg = {"node_f1": [], "edge_f1": [], "type_acc": [], "rel_acc": [], "parse_err": [], "latency": []}

    for scenario_name, results in all_results.items():
        for approach, label, overall in [
            ("freeform", "Free-form", overall_ff),
            ("controlled", "Ctrl Gen", overall_cg),
        ]:
            runs = results[approach]
            avg_node_f1 = statistics.mean(r["node_metrics"]["f1"] for r in runs)
            avg_edge_f1 = statistics.mean(r["edge_metrics"]["f1"] for r in runs)
            avg_type_acc = statistics.mean(r["node_metrics"]["type_accuracy"] for r in runs)
            avg_rel_acc = statistics.mean(r["edge_metrics"]["rel_accuracy"] for r in runs)
            avg_parse_err = statistics.mean(r["parsing_errors"] for r in runs)
            avg_latency = statistics.mean(r["latency_ms"] for r in runs)

            overall["node_f1"].append(avg_node_f1)
            overall["edge_f1"].append(avg_edge_f1)
            overall["type_acc"].append(avg_type_acc)
            overall["rel_acc"].append(avg_rel_acc)
            overall["parse_err"].append(avg_parse_err)
            overall["latency"].append(avg_latency)

            short_name = scenario_name[:33]
            print(f"{short_name:<35} | {label:<12} | {avg_node_f1:>8.3f} | {avg_edge_f1:>8.3f} | {avg_type_acc:>7.1%} | {avg_rel_acc:>7.1%} | {avg_parse_err:>9.1f} | {avg_latency:>7.0f}ms")
        print()

    # Overall averages
    print("─" * len(header))
    for label, overall in [("Free-form", overall_ff), ("Ctrl Gen", overall_cg)]:
        avg_nf1 = statistics.mean(overall["node_f1"])
        avg_ef1 = statistics.mean(overall["edge_f1"])
        avg_ta = statistics.mean(overall["type_acc"])
        avg_ra = statistics.mean(overall["rel_acc"])
        avg_pe = statistics.mean(overall["parse_err"])
        avg_lat = statistics.mean(overall["latency"])
        print(f"{'OVERALL AVERAGE':<35} | {label:<12} | {avg_nf1:>8.3f} | {avg_ef1:>8.3f} | {avg_ta:>7.1%} | {avg_ra:>7.1%} | {avg_pe:>9.1f} | {avg_lat:>7.0f}ms")

    # Delta analysis
    print("\n" + "=" * 100)
    print("DELTA ANALYSIS (Controlled Gen - Free-form)")
    print("=" * 100)
    delta_nf1 = statistics.mean(overall_cg["node_f1"]) - statistics.mean(overall_ff["node_f1"])
    delta_ef1 = statistics.mean(overall_cg["edge_f1"]) - statistics.mean(overall_ff["edge_f1"])
    delta_ta = statistics.mean(overall_cg["type_acc"]) - statistics.mean(overall_ff["type_acc"])
    delta_ra = statistics.mean(overall_cg["rel_acc"]) - statistics.mean(overall_ff["rel_acc"])
    delta_pe = statistics.mean(overall_cg["parse_err"]) - statistics.mean(overall_ff["parse_err"])
    delta_lat = statistics.mean(overall_cg["latency"]) - statistics.mean(overall_ff["latency"])

    print(f"  Node F1:        {delta_nf1:>+.3f}")
    print(f"  Edge F1:        {delta_ef1:>+.3f}")
    print(f"  Type Accuracy:  {delta_ta:>+.1%}")
    print(f"  Rel Accuracy:   {delta_ra:>+.1%}")
    print(f"  Parse Errors:   {delta_pe:>+.1f}")
    print(f"  Latency:        {delta_lat:>+.0f}ms")

    # Verdict
    print("\n" + "=" * 100)
    if delta_nf1 > 0.02 or delta_ef1 > 0.02:
        print("VERDICT: Controlled Generation shows meaningful improvement → WORTH IMPLEMENTING")
    elif delta_nf1 < -0.02 or delta_ef1 < -0.02:
        print("VERDICT: Controlled Generation REGRESSES quality → KEEP current approach")
    else:
        print("VERDICT: No significant difference → normalization layer is sufficient")
        if delta_pe < -0.5:
            print("         BUT: Controlled Gen eliminates parsing errors → consider for robustness")
    print("=" * 100)

    return all_results


if __name__ == "__main__":
    run_benchmark(n_runs=3)
