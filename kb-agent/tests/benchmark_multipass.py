"""
Benchmark: Multi-Pass Extraction for ArchiMate Graph Extraction

Tests whether running N independent extraction passes over the same document
and merging results (with deduplication) improves entity/edge recall.

Uses Controlled Generation (the winner from benchmark_controlled_gen.py) as
the extraction method, varying only the number of passes: 1, 2, 3.

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

from agents.processing import VALID_ENTITY_TYPES, VALID_RELATIONSHIP_TYPES
from tests.test_e2e_extraction_scenarios import ALL_SCENARIOS
from tests.test_graph_extraction import parse_node, parse_edge

# Reuse schema and metrics from controlled gen benchmark
from tests.benchmark_controlled_gen import (
    GraphExtraction,
    ExtractedNode,
    ExtractedEdge,
    EXTRACTION_PROMPT,
    compute_node_metrics,
    compute_edge_metrics,
)

# ---------------------------------------------------------------------------
# Multi-pass extraction with deduplication
# ---------------------------------------------------------------------------

def extract_multipass(
    client: genai.Client,
    document_text: str,
    n_passes: int = 1,
    temperature_spread: bool = True,
) -> tuple[dict, float]:
    """Run N independent extraction passes and merge results.

    Args:
        n_passes: Number of independent extraction passes.
        temperature_spread: If True, vary temperature slightly across passes
            (0.0, 0.2, 0.4) to encourage diversity.
    """
    prompt = EXTRACTION_PROMPT.format(document_text=document_text)

    all_nodes: dict[str, ExtractedNode] = {}  # "type:name_lower" -> node
    all_edges: dict[str, ExtractedEdge] = {}  # "src_type:src->rel->tgt_type:tgt" -> edge
    total_latency_ms = 0

    temps = [0.0, 0.2, 0.4, 0.6, 0.8] if temperature_spread else [0.0] * n_passes

    for p in range(n_passes):
        temp = temps[p] if p < len(temps) else 0.0

        start = time.time()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=temp,
                response_mime_type="application/json",
                response_schema=GraphExtraction,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
        )
        latency_ms = (time.time() - start) * 1000
        total_latency_ms += latency_ms

        try:
            data = json.loads(response.text)
            extraction = GraphExtraction(**data)
        except Exception as e:
            print(f"    Pass {p+1} failed: {e}")
            continue

        # Merge nodes (dedup by type + lowered name)
        for n in extraction.nodes:
            key = f"{n.entity_type}:{n.entity_name.lower().strip()}"
            if key not in all_nodes:
                all_nodes[key] = n

        # Merge edges (dedup by src_type:src + rel + tgt_type:tgt)
        for e in extraction.edges:
            key = (
                f"{e.source_type}:{e.source_name.lower().strip()}"
                f"->{e.relationship_type}->"
                f"{e.target_type}:{e.target_name.lower().strip()}"
            )
            if key not in all_edges:
                all_edges[key] = e

    # Convert to standard format
    nodes = [f"{n.entity_type}:{n.entity_name}" for n in all_nodes.values()]
    edges = []
    for e in all_edges.values():
        edge_str = f"{e.source_type}:{e.source_name}->{e.relationship_type}"
        if e.qualifier:
            edge_str += f"[{e.qualifier}]"
        edge_str += f"->{e.target_type}:{e.target_name}"
        edges.append(edge_str)

    return {
        "nodes": nodes,
        "edges": edges,
        "raw_node_count": len(all_nodes),
        "raw_edge_count": len(all_edges),
        "parsing_errors": 0,
        "schema_violations": 0,
        "passes": n_passes,
        "latency_ms": total_latency_ms,
    }, total_latency_ms


# ---------------------------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------------------------

def run_benchmark(n_runs: int = 3):
    """Run multi-pass benchmark: compare 1-pass vs 2-pass vs 3-pass."""
    client = genai.Client()
    pass_configs = [1, 2, 3]

    print("=" * 90)
    print("BENCHMARK: Multi-Pass Extraction (Controlled Gen, N=1 vs N=2 vs N=3)")
    print(f"Model: gemini-2.5-flash | Runs per scenario: {n_runs}")
    print("=" * 90)

    # {scenario_name: {n_passes: [run_results]}}
    all_results: dict[str, dict[int, list]] = {}

    for scenario in ALL_SCENARIOS:
        print(f"\n{'─' * 80}")
        print(f"Scenario: {scenario.name}")
        print(f"Ground truth: {len(scenario.expected_nodes)} nodes, {len(scenario.expected_edges)} edges")
        print(f"{'─' * 80}")

        all_results[scenario.name] = {}

        for n_passes in pass_configs:
            all_results[scenario.name][n_passes] = []

            for run in range(n_runs):
                label = f"  Run {run+1}/{n_runs} | {n_passes}-pass"
                print(f"{label}...", end=" ", flush=True)

                result, lat = extract_multipass(
                    client, scenario.document_text, n_passes=n_passes
                )
                node_m = compute_node_metrics(result["nodes"], scenario.expected_nodes)
                edge_m = compute_edge_metrics(result["edges"], scenario.expected_edges)
                result["node_metrics"] = node_m
                result["edge_metrics"] = edge_m
                all_results[scenario.name][n_passes].append(result)

                print(
                    f"{lat:.0f}ms | "
                    f"nodes={result['raw_node_count']} F1={node_m['f1']:.3f} (R={node_m['recall']:.3f}) | "
                    f"edges={result['raw_edge_count']} F1={edge_m['f1']:.3f} (R={edge_m['recall']:.3f})"
                )

    # ---------------------------------------------------------------------------
    # Summary table
    # ---------------------------------------------------------------------------
    print("\n\n" + "=" * 110)
    print(f"SUMMARY TABLE (averaged over {n_runs} runs)")
    print("=" * 110)

    header = (
        f"{'Scenario':<35} | {'Passes':>6} | {'Nodes':>5} | {'Node F1':>8} | {'Node Rec':>8} | "
        f"{'Edges':>5} | {'Edge F1':>8} | {'Edge Rec':>8} | {'Latency':>8}"
    )
    print(header)
    print("─" * len(header))

    # For overall averages
    overall: dict[int, dict[str, list]] = {
        p: {"node_f1": [], "node_rec": [], "edge_f1": [], "edge_rec": [], "nodes": [], "edges": [], "latency": []}
        for p in pass_configs
    }

    for scenario_name, pass_results in all_results.items():
        for n_passes in pass_configs:
            runs = pass_results[n_passes]
            avg_nf1 = statistics.mean(r["node_metrics"]["f1"] for r in runs)
            avg_nrec = statistics.mean(r["node_metrics"]["recall"] for r in runs)
            avg_ef1 = statistics.mean(r["edge_metrics"]["f1"] for r in runs)
            avg_erec = statistics.mean(r["edge_metrics"]["recall"] for r in runs)
            avg_nodes = statistics.mean(r["raw_node_count"] for r in runs)
            avg_edges = statistics.mean(r["raw_edge_count"] for r in runs)
            avg_lat = statistics.mean(r["latency_ms"] for r in runs)

            overall[n_passes]["node_f1"].append(avg_nf1)
            overall[n_passes]["node_rec"].append(avg_nrec)
            overall[n_passes]["edge_f1"].append(avg_ef1)
            overall[n_passes]["edge_rec"].append(avg_erec)
            overall[n_passes]["nodes"].append(avg_nodes)
            overall[n_passes]["edges"].append(avg_edges)
            overall[n_passes]["latency"].append(avg_lat)

            short = scenario_name[:33]
            print(
                f"{short:<35} | {n_passes:>6} | {avg_nodes:>5.0f} | {avg_nf1:>8.3f} | {avg_nrec:>8.3f} | "
                f"{avg_edges:>5.0f} | {avg_ef1:>8.3f} | {avg_erec:>8.3f} | {avg_lat:>7.0f}ms"
            )
        print()

    # Overall
    print("─" * len(header))
    for n_passes in pass_configs:
        o = overall[n_passes]
        print(
            f"{'OVERALL AVERAGE':<35} | {n_passes:>6} | "
            f"{statistics.mean(o['nodes']):>5.0f} | "
            f"{statistics.mean(o['node_f1']):>8.3f} | {statistics.mean(o['node_rec']):>8.3f} | "
            f"{statistics.mean(o['edges']):>5.0f} | "
            f"{statistics.mean(o['edge_f1']):>8.3f} | {statistics.mean(o['edge_rec']):>8.3f} | "
            f"{statistics.mean(o['latency']):>7.0f}ms"
        )

    # Delta analysis
    print("\n" + "=" * 110)
    print("DELTA ANALYSIS (vs 1-pass baseline)")
    print("=" * 110)
    base = overall[1]
    for n_passes in [2, 3]:
        o = overall[n_passes]
        dnf1 = statistics.mean(o["node_f1"]) - statistics.mean(base["node_f1"])
        dnrec = statistics.mean(o["node_rec"]) - statistics.mean(base["node_rec"])
        def1 = statistics.mean(o["edge_f1"]) - statistics.mean(base["edge_f1"])
        derec = statistics.mean(o["edge_rec"]) - statistics.mean(base["edge_rec"])
        dlat = statistics.mean(o["latency"]) - statistics.mean(base["latency"])
        cost_mult = statistics.mean(o["latency"]) / statistics.mean(base["latency"])

        print(f"\n  {n_passes}-pass vs 1-pass:")
        print(f"    Node F1:     {dnf1:>+.3f}")
        print(f"    Node Recall: {dnrec:>+.3f}")
        print(f"    Edge F1:     {def1:>+.3f}")
        print(f"    Edge Recall: {derec:>+.3f}")
        print(f"    Latency:     {dlat:>+.0f}ms ({cost_mult:.1f}x cost)")

    # Verdict
    print("\n" + "=" * 110)
    base_nrec = statistics.mean(base["node_rec"])
    p3_nrec = statistics.mean(overall[3]["node_rec"])
    p3_erec = statistics.mean(overall[3]["edge_rec"])
    base_erec = statistics.mean(base["edge_rec"])

    if (p3_nrec - base_nrec) > 0.05 or (p3_erec - base_erec) > 0.05:
        print("VERDICT: Multi-pass significantly improves recall → WORTH THE COST for large documents")
    elif (p3_nrec - base_nrec) > 0.02 or (p3_erec - base_erec) > 0.02:
        print("VERDICT: Multi-pass shows marginal recall improvement → CONSIDER for docs > 10 pages")
    else:
        print("VERDICT: Multi-pass does NOT improve recall meaningfully → NOT WORTH the cost multiplier")
    print("=" * 110)

    return all_results


if __name__ == "__main__":
    run_benchmark(n_runs=3)
