"""KB Evaluation Runner — orchestrates all 3 evaluation layers.

Usage:
  # Full evaluation (all 3 layers)
  python run_eval.py

  # Single layer
  python run_eval.py --layer L1
  python run_eval.py --layer L2
  python run_eval.py --layer L3

  # Evaluation on specific split (dev or test)
  python run_eval.py --layer L2 --split dev
  python run_eval.py --layer L2 --split test

  # Generate test PDFs first
  python run_eval.py --generate-data
"""
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kb-agent"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "kb-agent", ".env"), override=True)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def generate_test_data():
    """Generate ArchiSurance test PDFs and ground truth."""
    print("=" * 60)
    print("GENERATING TEST DATA")
    print("=" * 60)
    from data.archisurance.generate_test_docs import main as gen_main
    gen_main()
    print()


def run_l1():
    """L1: KG Construction Quality."""
    print("=" * 60)
    print("L1: KNOWLEDGE GRAPH CONSTRUCTION QUALITY")
    print("=" * 60)
    from metrics.kg_quality import run
    return run()


def run_l2(split: str = "all"):
    """L2: Retrieval Quality (Graph vs Vector A/B)."""
    print("=" * 60)
    print(f"L2: RETRIEVAL QUALITY — GRAPH vs VECTOR A/B (split={split})")
    print("=" * 60)
    from metrics.retrieval_quality import run
    return run(split=split)


def run_l3():
    """L3: Answer Quality (LLM-as-Judge)."""
    print("=" * 60)
    print("L3: ANSWER QUALITY — LLM-AS-JUDGE")
    print("=" * 60)
    from metrics.answer_quality import run
    return run()


def print_summary(all_results: dict):
    """Print a concise evaluation summary."""
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)

    if "L1_KG_Construction" in all_results:
        l1 = all_results["L1_KG_Construction"]
        ef1 = l1["entity_f1"]
        print(f"\nL1 — KG Construction:")
        print(f"  Entity Micro-F1:    {ef1['micro_f1']}")
        print(f"  Entity Macro-F1:    {ef1['macro_f1']}")
        print(f"  Extracted/GT:       {ef1['total_extracted']}/{ef1['total_ground_truth']}")
        print(f"  Rel Type Coverage:  {l1['relationship_f1']['type_coverage']}")
        print(f"  Duplicate Entities: {l1['entity_resolution']['total_duplicate_entities']}")
        if "confidence_distribution" in l1:
            cd = l1["confidence_distribution"]
            print(f"  Edge Confidence:    {cd['pct_extracted']}% EXTRACTED, {cd['pct_inferred']}% INFERRED, {cd['pct_ambiguous']}% AMBIGUOUS, {cd['pct_null']}% NULL")

    if "L2_Retrieval_Quality" in all_results:
        l2 = all_results["L2_Retrieval_Quality"]["aggregates"]
        print(f"\nL2 — Retrieval Quality:")
        if "arms" in l2:
            arms = l2["arms"]
            print(f"  Graph Pipeline Recall: {arms.get('graph', {}).get('avg_recall', 'N/A')}")
            print(f"  Vector-Only Recall:    {arms.get('vector_only', {}).get('avg_recall', 'N/A')}")
            print(f"  Oracle Recall (ceil):  {arms.get('oracle', {}).get('avg_recall', 'N/A')}")
            print(f"  Blind Recall (floor):  {arms.get('blind', {}).get('avg_recall', 'N/A')}")
            print(f"  Constant Baseline:     {arms.get('constant', {}).get('avg_recall', 'N/A')}")
            print(f"  Winner Arm:            {l2.get('winner', 'N/A')}")
        else:
            print(f"  Full Pipeline Recall: {l2.get('avg_full_pipeline_recall')}")
            print(f"  Vector-Only Recall:   {l2.get('avg_vector_only_recall')}")

        print(f"  Graph Uplift (avg):    {l2.get('avg_graph_uplift', 0.0):+.3f}")
        print(f"  Multi-hop Uplift:      {l2.get('avg_multihop_uplift', 0.0):+.3f}")
        print(f"  Graph Helps in:        {l2.get('questions_where_graph_helps', 0)}/{l2.get('questions_total', 0)} questions")

        if "attrition" in l2:
            att_counts = l2["attrition"].get("counts", {})
            att_shares = l2["attrition"].get("shares", {})
            print(f"  Graph Attrition:")
            for bucket, cnt in att_counts.items():
                sh = att_shares.get(bucket, 0.0)
                print(f"    - {bucket:23s}: {cnt:2d} ({sh*100:5.1f}%)")

        if "candidate_pool_distribution" in l2:
            cpd = l2["candidate_pool_distribution"]
            print(f"  Candidate Pool Dist:   min={cpd.get('min')} med={cpd.get('median')} p90={cpd.get('p90')} max={cpd.get('max')} (cap={cpd.get('configured_limit')})")

    if "L3_Answer_Quality" in all_results:
        l3 = all_results["L3_Answer_Quality"]["aggregates"]
        print(f"\nL3 — Answer Quality (0-5 scale):")
        print(f"  Faithfulness:    {l3['avg_faithfulness']}/5")
        print(f"  Relevancy:       {l3['avg_relevancy']}/5")
        print(f"  Correctness:     {l3['avg_correctness']}/5")
        print(f"  Overall:         {l3['overall_score']}/5")

    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="KB Evaluation Runner")
    parser.add_argument("--layer", choices=["L1", "L2", "L3"], help="Run single layer")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="all", help="Dataset split (L2)")
    parser.add_argument("--generate-data", action="store_true", help="Generate test PDFs")
    args = parser.parse_args()

    if args.generate_data:
        generate_test_data()
        return

    os.makedirs(RESULTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_results = {}

    start = time.perf_counter()

    if args.layer in (None, "L1"):
        l1 = run_l1()
        all_results[l1["layer"]] = l1
        print()

    if args.layer in (None, "L2"):
        l2 = run_l2(split=args.split)
        all_results[l2["layer"]] = l2
        print()

    if args.layer in (None, "L3"):
        l3 = run_l3()
        all_results[l3["layer"]] = l3
        print()

    elapsed = time.perf_counter() - start

    # Save results
    all_results["metadata"] = {
        "timestamp": timestamp,
        "elapsed_seconds": round(elapsed, 1),
        "layers_run": list(all_results.keys()),
        "split": args.split,
    }

    out_path = os.path.join(RESULTS_DIR, f"eval_{timestamp}.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"Results saved: {out_path}")

    print_summary(all_results)


if __name__ == "__main__":
    main()
