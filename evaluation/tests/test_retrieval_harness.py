"""Unit tests for the evaluation harness: diagnostic arms, pure scoring, attrition decomposition, sweeps, split enforcement, and error propagation."""

import pytest

try:
    from evaluation.constants import (
        DEFAULT_CANDIDATE_LIMIT,
        DEFAULT_TOP_K,
        DEFAULT_CONTEXT_TRUNCATION_LIMIT,
        DEFAULT_MIN_GRAPH_PATHS,
        DEFAULT_SPLIT_SEED,
        DEFAULT_DEV_RATIO,
        CANDIDATE_LIMIT_SWEEP_VALUES,
    )
    from evaluation.metrics.retrieval_quality import (
        compute_context_recall,
        compute_uplift,
        compute_percentiles,
        score_question_arms,
        decompose_graph_attrition,
        aggregate_evaluation_results,
        sweep_candidate_limit,
        split_dataset,
        filter_questions_by_split,
        run_l2_evaluation,
    )
except ImportError:
    from constants import (
        DEFAULT_CANDIDATE_LIMIT,
        DEFAULT_TOP_K,
        DEFAULT_CONTEXT_TRUNCATION_LIMIT,
        DEFAULT_MIN_GRAPH_PATHS,
        DEFAULT_SPLIT_SEED,
        DEFAULT_DEV_RATIO,
        CANDIDATE_LIMIT_SWEEP_VALUES,
    )
    from metrics.retrieval_quality import (
        compute_context_recall,
        compute_uplift,
        compute_percentiles,
        score_question_arms,
        decompose_graph_attrition,
        aggregate_evaluation_results,
        sweep_candidate_limit,
        split_dataset,
        filter_questions_by_split,
        run_l2_evaluation,
    )


def test_compute_context_recall_basic():
    chunks = [
        "Claims Management Platform connects to Claims Registration.",
        "Some irrelevant chunk about billing.",
    ]
    expected_entities = ["Claims Management Platform", "Claims Registration", "Claims Assessment"]

    # 2 out of 3 found
    recall = compute_context_recall(chunks, expected_entities)
    assert recall == pytest.approx(0.667, abs=1e-3)

    # Empty expected entities should return 1.0
    assert compute_context_recall(chunks, []) == 1.0

    # No chunks found
    assert compute_context_recall([], expected_entities) == 0.0


def test_compute_context_recall_dict_and_case_insensitive():
    chunks = [
        {"text": "CLAIMS MANAGEMENT PLATFORM is an application."},
        {"text": "Underwriting Team evaluates risk."},
    ]
    expected = ["Claims Management Platform", "underwriting team"]
    assert compute_context_recall(chunks, expected) == 1.0


def test_compute_uplift():
    assert compute_uplift(0.8, 0.5) == pytest.approx(0.3, abs=1e-3)
    assert compute_uplift(0.5, 0.8) == pytest.approx(-0.3, abs=1e-3)
    assert compute_uplift(0.5, 0.5) == pytest.approx(0.0, abs=1e-3)


def test_compute_percentiles():
    # Empty
    assert compute_percentiles([]) == {"min": 0, "median": 0, "p90": 0, "max": 0}

    # Odd length
    vals = [10, 20, 30, 40, 50]
    p = compute_percentiles(vals)
    assert p["min"] == 10
    assert p["median"] == 30
    assert p["max"] == 50
    assert p["p90"] == 46.0

    # Even length
    vals2 = [10, 20, 30, 40]
    p2 = compute_percentiles(vals2)
    assert p2["min"] == 10
    assert p2["median"] == 25.0
    assert p2["max"] == 40


def test_diagnostic_arms_scoring():
    q = {
        "id": "q1",
        "question": "What connects to X?",
        "expected_entities": ["EntityA", "EntityB"],
    }
    graph_chunks = ["EntityA is connected to EntityB."]
    vector_chunks = ["EntityA is here."]

    arms = score_question_arms(
        q=q,
        graph_chunks=graph_chunks,
        vector_chunks=vector_chunks,
        all_eval_questions=[q],
        graph_time_ms=12.5,
        vector_time_ms=5.2,
    )

    # Check graph arm
    assert arms["graph"]["context_recall"] == 1.0
    assert arms["graph"]["chunks_found"] == 1
    assert arms["graph"]["time_ms"] == 12.5
    assert arms["graph"]["is_reference"] is False

    # Check vector_only arm
    assert arms["vector_only"]["context_recall"] == 0.5
    assert arms["vector_only"]["chunks_found"] == 1
    assert arms["vector_only"]["time_ms"] == 5.2
    assert arms["vector_only"]["is_reference"] is False

    # Check oracle arm (reference point: all expected entities present)
    assert arms["oracle"]["context_recall"] == 1.0
    assert arms["oracle"]["is_reference"] is True

    # Check blind arm (reference point: empty context)
    assert arms["blind"]["context_recall"] == 0.0
    assert arms["blind"]["is_reference"] is True

    # Check constant arm (majority class / constant baseline)
    assert "constant" in arms
    assert arms["constant"]["is_reference"] is False


def test_diagnostic_arms_scoring_without_questions_list():
    q = {"id": "q1", "expected_entities": ["EntityA"]}
    arms = score_question_arms(
        q=q,
        graph_chunks=["EntityA"],
        vector_chunks=[],
        all_eval_questions=None,
    )
    assert arms["constant"]["context_recall"] == 0.0


def test_attrition_decomposition_buckets():
    # C0_no_entities: question has no expected entities
    q_c0 = {"id": "q_c0", "expected_entities": []}
    bucket_c0 = decompose_graph_attrition(
        q=q_c0,
        candidate_pool=[],
        top_k_chunks=[],
        candidate_pool_size=0,
        configured_limit=40,
    )
    assert bucket_c0 == "C0_no_entities"

    # hit: all expected entities retrieved in top-k
    q_hit = {"id": "q_hit", "expected_entities": ["Alpha", "Beta"]}
    topk_hit = ["Alpha and Beta are here."]
    pool_hit = topk_hit
    bucket_hit = decompose_graph_attrition(
        q=q_hit,
        candidate_pool=pool_hit,
        top_k_chunks=topk_hit,
        candidate_pool_size=len(pool_hit),
        configured_limit=40,
    )
    assert bucket_hit == "hit"

    # C1_entity_never_in_pool: expected entity never appears in candidate pool
    q_c1 = {"id": "q_c1", "expected_entities": ["Alpha", "Beta"]}
    pool_c1 = ["Only Gamma is here."]
    topk_c1 = pool_c1
    bucket_c1 = decompose_graph_attrition(
        q=q_c1,
        candidate_pool=pool_c1,
        top_k_chunks=topk_c1,
        candidate_pool_size=len(pool_c1),
        configured_limit=40,
    )
    assert bucket_c1 == "C1_entity_never_in_pool"

    # C2_below_topk: expected entity is in candidate pool, but not in returned top-k
    q_c2 = {"id": "q_c2", "expected_entities": ["Alpha", "Beta"]}
    pool_c2 = ["Alpha is here.", "Beta is further down."]
    topk_c2 = ["Alpha is here."]  # Beta not in topk
    bucket_c2 = decompose_graph_attrition(
        q=q_c2,
        candidate_pool=pool_c2,
        top_k_chunks=topk_c2,
        candidate_pool_size=len(pool_c2),
        configured_limit=40,
    )
    assert bucket_c2 == "C2_below_topk"

    # C3_capped_by_limit: candidate pool was truncated by configured limit constant
    # (i.e. raw candidate pool reached or exceeded the limit, and not all entities in top-k)
    q_c3 = {"id": "q_c3", "expected_entities": ["Alpha", "Beta"]}
    pool_c3 = ["Alpha is here."]  # Beta missed because pool was capped
    topk_c3 = ["Alpha is here."]
    bucket_c3 = decompose_graph_attrition(
        q=q_c3,
        candidate_pool=pool_c3,
        top_k_chunks=topk_c3,
        candidate_pool_size=40,  # reached the configured limit
        configured_limit=40,
        pool_was_truncated=True,
    )
    assert bucket_c3 == "C3_capped_by_limit"


def test_aggregation_and_distribution():
    per_question_results = [
        {
            "id": "q1",
            "category": "single_hop",
            "requires_graph": False,
            "arms": {
                "graph": {"context_recall": 1.0, "time_ms": 10.0, "is_reference": False},
                "vector_only": {"context_recall": 0.5, "time_ms": 5.0, "is_reference": False},
                "oracle": {"context_recall": 1.0, "is_reference": True},
                "blind": {"context_recall": 0.0, "is_reference": True},
                "constant": {"context_recall": 0.5, "is_reference": False},
            },
            "graph_uplift": 0.5,
            "attrition_bucket": "hit",
            "candidate_pool_size": 25,
        },
        {
            "id": "q2",
            "category": "multi_hop",
            "requires_graph": True,
            "arms": {
                "graph": {"context_recall": 0.5, "time_ms": 12.0, "is_reference": False},
                "vector_only": {"context_recall": 0.5, "time_ms": 6.0, "is_reference": False},
                "oracle": {"context_recall": 1.0, "is_reference": True},
                "blind": {"context_recall": 0.0, "is_reference": True},
                "constant": {"context_recall": 0.5, "is_reference": False},
            },
            "graph_uplift": 0.0,
            "attrition_bucket": "C1_entity_never_in_pool",
            "candidate_pool_size": 35,
        },
    ]

    agg = aggregate_evaluation_results(per_question_results, configured_limit=40)

    # Check arm averages
    assert agg["arms"]["graph"]["avg_recall"] == pytest.approx(0.75, abs=1e-3)
    assert agg["arms"]["vector_only"]["avg_recall"] == pytest.approx(0.5, abs=1e-3)
    assert agg["arms"]["oracle"]["avg_recall"] == pytest.approx(1.0, abs=1e-3)
    assert agg["arms"]["blind"]["avg_recall"] == pytest.approx(0.0, abs=1e-3)
    assert agg["arms"]["constant"]["avg_recall"] == pytest.approx(0.5, abs=1e-3)

    # Reference arms excluded from winner selection
    assert agg["winner"] == "graph"  # between graph and vector_only

    # Check attrition breakdown
    assert agg["attrition"]["counts"]["hit"] == 1
    assert agg["attrition"]["counts"]["C1_entity_never_in_pool"] == 1
    assert agg["attrition"]["shares"]["hit"] == 0.5

    # Check pool distribution
    dist = agg["candidate_pool_distribution"]
    assert dist["min"] == 25
    assert dist["max"] == 35
    assert dist["configured_limit"] == 40
    assert dist["cap_inside_distribution"] is False  # 40 is > max (35)
    assert "median" in dist
    assert "p90" in dist


def test_aggregation_empty():
    agg = aggregate_evaluation_results([], configured_limit=40)
    assert agg["questions_total"] == 0
    assert agg["winner"] == "none"


def test_sweep_candidate_limit():
    # Synthetic candidate data per question
    records = [
        {
            "id": "q1",
            "expected_entities": ["Alpha", "Beta"],
            "candidates": [
                {"text": "Alpha is here", "score": 0.9},
                {"text": "Beta is here", "score": 0.8},
                {"text": "Irrelevant", "score": 0.1},
            ],
            "vector_chunks": ["Alpha is here"],
        },
        {
            "id": "q2",
            "expected_entities": ["Gamma", "Delta"],
            "candidates": [
                {"text": "Gamma is here", "score": 0.9},
                {"text": "Noise 1", "score": 0.8},
                {"text": "Delta is here", "score": 0.7},
            ],
            "vector_chunks": [],
        },
    ]

    sweep_results = sweep_candidate_limit(records, limits=[1, 2, 3])
    assert len(sweep_results) == 3
    # With limit 1, neither question finds all entities
    assert sweep_results[0]["limit"] == 1
    assert sweep_results[0]["avg_graph_recall"] < sweep_results[2]["avg_graph_recall"]


def test_split_dataset_and_enforcement():
    questions = [{"id": f"q_{i}", "category": "test"} for i in range(20)]

    split_map = split_dataset(questions, seed=42, dev_ratio=0.5)
    dev_ids = {q_id for q_id, s in split_map.items() if s == "dev"}
    test_ids = {q_id for q_id, s in split_map.items() if s == "test"}

    assert len(dev_ids) == 10
    assert len(test_ids) == 10
    assert dev_ids.isdisjoint(test_ids)

    # Filter by split
    dev_questions = filter_questions_by_split(questions, split="dev", split_map=split_map)
    assert len(dev_questions) == 10
    assert all(split_map[q["id"]] == "dev" for q in dev_questions)

    test_questions = filter_questions_by_split(questions, split="test", split_map=split_map)
    assert len(test_questions) == 10
    assert all(split_map[q["id"]] == "test" for q in test_questions)

    all_questions = filter_questions_by_split(questions, split="all", split_map=split_map)
    assert len(all_questions) == 20

    with pytest.raises(ValueError, match="Invalid split"):
        filter_questions_by_split(questions, split="invalid")

    # Reporting call cannot read dev when split='test' is enforced
    with pytest.raises(ValueError, match="Reporting is strictly restricted to test split"):
        filter_questions_by_split(dev_questions, split="test", split_map=split_map, enforce_test_only_reporting=True)


def test_search_failure_invalidates_run():
    # If full pipeline search raises an exception, run_l2_evaluation must raise
    def failing_full_search_fn(query):
        raise ConnectionError("Spanner connection dropped")

    questions = [{"id": "q1", "question": "test", "expected_entities": ["A"]}]

    with pytest.raises(ConnectionError):
        run_l2_evaluation(
            questions=questions,
            search_full_fn=failing_full_search_fn,
            search_vector_fn=lambda q: {"semantically_similar_chunks": []},
        )

    # If vector-only search raises an exception, run_l2_evaluation must also raise
    def failing_vector_search_fn(query):
        raise RuntimeError("Vector search failed")

    with pytest.raises(RuntimeError):
        run_l2_evaluation(
            questions=questions,
            search_full_fn=lambda q: {"semantically_similar_chunks": []},
            search_vector_fn=failing_vector_search_fn,
        )


def test_run_l2_evaluation_end_to_end_synthetic():
    questions = [
        {
            "id": "q_syn_1",
            "question": "What connects to Alpha?",
            "expected_entities": ["Alpha", "Beta"],
            "category": "single_hop",
            "hop_count": 1,
            "requires_graph": False,
        },
        {
            "id": "q_syn_2",
            "question": "What is Gamma?",
            "expected_entities": ["Gamma"],
            "category": "multi_hop",
            "hop_count": 2,
            "requires_graph": True,
        },
    ]

    def mock_full_search(q_text):
        if "Alpha" in q_text:
            chunks = ["Alpha connects to Beta.", "Extra context."]
        else:
            chunks = ["Gamma is a system component."]
        return {
            "semantically_similar_chunks": chunks,
            "graph_connections": ["Alpha -> Beta"],
            "candidate_pool": chunks,
            "candidate_pool_size": len(chunks),
        }

    def mock_vector_search(q_text):
        if "Alpha" in q_text:
            chunks = ["Alpha is present."]
        else:
            chunks = ["Gamma is here."]
        return {
            "semantically_similar_chunks": chunks,
            "candidate_pool": chunks,
            "candidate_pool_size": len(chunks),
        }

    eval_result = run_l2_evaluation(
        questions=questions,
        search_full_fn=mock_full_search,
        search_vector_fn=mock_vector_search,
        configured_limit=40,
        top_k=15,
    )

    assert eval_result["layer"] == "L2_Retrieval_Quality"
    assert len(eval_result["per_question"]) == 2
    agg = eval_result["aggregates"]
    assert agg["questions_total"] == 2
    assert agg["arms"]["graph"]["avg_recall"] == 1.0
    assert agg["arms"]["vector_only"]["avg_recall"] == 0.75
    assert agg["avg_graph_uplift"] == 0.25
    assert agg["attrition"]["counts"]["hit"] == 2


def test_import_regression_from_evaluation_entrypoint():
    """Regression test: importing metrics.retrieval_quality from evaluation/ entrypoint must succeed."""
    import subprocess
    import sys
    from pathlib import Path

    eval_dir = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        "-c",
        "import sys; sys.path.insert(0, '../kb-agent'); import metrics.retrieval_quality",
    ]
    result = subprocess.run(cmd, cwd=str(eval_dir), capture_output=True, text=True)
    assert result.returncode == 0, f"Subprocess failed with stderr:\n{result.stderr}"

