"""Per-request cost tracking for Gemini API calls, embeddings, reranking, and Spanner.

Uses contextvars for thread-safe per-request accumulation.
Costs are aggregated per operation (ingestion or query) and persisted to Spanner.
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from google.cloud.spanner_v1 import COMMIT_TIMESTAMP

logger = logging.getLogger(__name__)

# ── Pricing constants (Google AI Studio, April 2026) ──
# Source: https://ai.google.dev/gemini-api/docs/pricing
# gemini-2.5-flash
FLASH_INPUT_PER_MTK = 0.30        # $/1M input tokens (standard, text/image/video)
FLASH_OUTPUT_PER_MTK = 2.50       # $/1M output tokens (standard)
FLASH_FLEX_INPUT_PER_MTK = 0.15   # $/1M input tokens (batch/flex)
FLASH_FLEX_OUTPUT_PER_MTK = 1.25  # $/1M output tokens (batch/flex)

# gemini-embedding-2-preview
EMBED_TEXT_PER_MTK = 0.20         # $/1M tokens (text)
EMBED_IMAGE_PER_MTK = 0.45        # $/1M tokens (images)

# Vertex AI semantic-ranker-512
RERANK_PER_REQUEST = 0.001        # $/request (approximate)

# Spanner (approximate per operation)
SPANNER_READ_PER_10K = 0.10       # $/10K read units
SPANNER_WRITE_PER_10K = 0.10      # $/10K write units

# Token estimation for embeddings (no usage_metadata available)
CHARS_PER_TOKEN = 4  # ~4 characters per token for English text


@dataclass
class ApiCallRecord:
    api: str            # "generate", "embed", "rerank", "spanner_read", "spanner_write"
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    estimated_cost_usd: float = 0.0
    detail: str = ""


@dataclass
class CostAccumulator:
    """Accumulates costs for a single operation (ingestion or query)."""
    calls: list[ApiCallRecord] = field(default_factory=list)
    spanner_reads: int = 0
    spanner_writes: int = 0

    def track_generate(self, response, model: str = "gemini-2.5-flash", tier: str = "standard"):
        """Track a generate_content call using response.usage_metadata.

        Extracts prompt_token_count, candidates_token_count, thoughts_token_count,
        and cached_content_token_count from the Gemini response.
        """
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0
        thinking_tokens = 0
        try:
            usage = response.usage_metadata
            if usage:
                input_tokens = getattr(usage, "prompt_token_count", 0) or 0
                output_tokens = getattr(usage, "candidates_token_count", 0) or 0
                cached_tokens = getattr(usage, "cached_content_token_count", 0) or 0
                thinking_tokens = getattr(usage, "thoughts_token_count", 0) or 0
        except Exception:
            pass

        # Billable input = prompt - cached (cached tokens are free)
        billable_input = max(0, input_tokens - cached_tokens)
        # Output includes thinking tokens (billed at output rate)
        billable_output = output_tokens + thinking_tokens

        if tier == "flex":
            cost = (billable_input * FLASH_FLEX_INPUT_PER_MTK + billable_output * FLASH_FLEX_OUTPUT_PER_MTK) / 1_000_000
        else:
            cost = (billable_input * FLASH_INPUT_PER_MTK + billable_output * FLASH_OUTPUT_PER_MTK) / 1_000_000

        self.calls.append(ApiCallRecord(
            api="generate", model=model,
            input_tokens=input_tokens, output_tokens=output_tokens + thinking_tokens,
            cached_tokens=cached_tokens, estimated_cost_usd=cost,
            detail=f"thinking={thinking_tokens}" if thinking_tokens else "",
        ))

    def track_embed(self, texts: list[str] | str, model: str = "gemini-embedding-2",
                    is_image: bool = False):
        """Track an embed_content call. Estimates tokens from text length."""
        if isinstance(texts, str):
            texts = [texts]
        total_chars = sum(len(t) for t in texts if isinstance(t, str))
        estimated_tokens = max(1, total_chars // CHARS_PER_TOKEN)
        price = EMBED_IMAGE_PER_MTK if is_image else EMBED_TEXT_PER_MTK
        cost = estimated_tokens * price / 1_000_000

        self.calls.append(ApiCallRecord(
            api="embed", model=model,
            input_tokens=estimated_tokens, estimated_cost_usd=cost,
        ))

    def track_rerank(self, num_records: int = 0):
        """Track a Vertex AI reranking call."""
        self.calls.append(ApiCallRecord(
            api="rerank", model="semantic-ranker-512",
            estimated_cost_usd=RERANK_PER_REQUEST,
            detail=f"{num_records} records",
        ))

    def track_spanner_read(self, count: int = 1):
        """Track Spanner read operations."""
        self.spanner_reads += count

    def track_spanner_write(self, mutations: int = 0):
        """Track Spanner write operations."""
        self.spanner_writes += mutations

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def total_embed_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls if c.api == "embed")

    @property
    def total_cost_usd(self) -> float:
        api_cost = sum(c.estimated_cost_usd for c in self.calls)
        spanner_cost = (self.spanner_reads * SPANNER_READ_PER_10K / 10_000
                        + self.spanner_writes * SPANNER_WRITE_PER_10K / 10_000)
        return api_cost + spanner_cost

    def to_dict(self) -> dict:
        """Export as dict for API response / Spanner storage."""
        breakdown = {}
        for c in self.calls:
            key = c.api
            if key not in breakdown:
                breakdown[key] = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
            breakdown[key]["calls"] += 1
            breakdown[key]["input_tokens"] += c.input_tokens
            breakdown[key]["output_tokens"] += c.output_tokens
            breakdown[key]["cost_usd"] += c.estimated_cost_usd

        return {
            "total_cost_usd": round(self.total_cost_usd, 6),
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "embed_tokens": self.total_embed_tokens,
            "spanner_reads": self.spanner_reads,
            "spanner_writes": self.spanner_writes,
            "breakdown": breakdown,
        }


# ── Module-level tracker (same reason as tenant_context: ADK thread pool compat) ──
_current_tracker: CostAccumulator | None = None


def start_tracking() -> CostAccumulator:
    """Start a new cost tracker for the current request."""
    global _current_tracker
    _current_tracker = CostAccumulator()
    return _current_tracker


def get_tracker() -> CostAccumulator | None:
    """Get the current request's cost tracker (None if not tracking)."""
    return _current_tracker


def stop_tracking() -> CostAccumulator | None:
    """Stop tracking and return the accumulated costs."""
    global _current_tracker
    tracker = _current_tracker
    _current_tracker = None
    return tracker


def save_cost_log(
    tenant_id: str,
    operation_type: str,
    operation_id: str,
    tracker: CostAccumulator,
) -> None:
    """Persist cost log to Spanner CostLog table."""
    try:
        from services.spanner_client import get_database
        database = get_database()
        data = tracker.to_dict()
        log_id = str(uuid.uuid4())
        database.run_in_transaction(lambda txn: txn.insert(
            "CostLog",
            columns=[
                "log_id", "tenant_id", "operation_type", "operation_id",
                "total_cost_usd", "input_tokens", "output_tokens",
                "embed_tokens", "spanner_reads", "spanner_writes",
                "breakdown", "created_at",
            ],
            values=[[
                log_id, tenant_id, operation_type, operation_id,
                data["total_cost_usd"], data["input_tokens"], data["output_tokens"],
                data["embed_tokens"], data["spanner_reads"], data["spanner_writes"],
                json.dumps(data["breakdown"]),
                COMMIT_TIMESTAMP,
            ]],
        ))
        logger.info(f"Cost log saved: {operation_type}/{operation_id} = ${data['total_cost_usd']:.4f}")
    except Exception as e:
        logger.warning(f"Failed to save cost log: {e}")
