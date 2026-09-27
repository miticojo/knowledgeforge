"""Constants for the evaluation harness.

Centralized home for tunable constants: candidate pool limits, top-k values,
context truncation lengths, and graph path limits.
"""

# Default candidate pool limit (e.g. ScaNN / RRF retrieval pool before reranking)
DEFAULT_CANDIDATE_LIMIT: int = 40

# Default top-k chunks returned to the generator / evaluated
DEFAULT_TOP_K: int = 15

# Context truncation limit per chunk in characters
DEFAULT_CONTEXT_TRUNCATION_LIMIT: int = 1500

# Minimum number of graph paths / chains required for graph traversal
DEFAULT_MIN_GRAPH_PATHS: int = 1

# Standard candidate limit values for parameter sweeps
CANDIDATE_LIMIT_SWEEP_VALUES: list[int] = [5, 10, 15, 20, 30, 40, 50, 60, 100]

# Standard top-k values for parameter sweeps
TOP_K_SWEEP_VALUES: list[int] = [3, 5, 10, 15, 20, 30]

# Standard random seed for deterministic dev/test splits
DEFAULT_SPLIT_SEED: int = 42

# Default dev/test split ratio (e.g., 0.5 = 50% dev, 50% test)
DEFAULT_DEV_RATIO: float = 0.5
