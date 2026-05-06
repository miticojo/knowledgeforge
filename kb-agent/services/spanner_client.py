"""Cloud Spanner client singleton for the Agentic Knowledge Base.

Provides lazy-initialized database access with helpers for read and write operations.
Uses environment variables for configuration:
- GOOGLE_CLOUD_PROJECT (default: from gcloud config)
- SPANNER_INSTANCE
- SPANNER_DATABASE
"""
import os
import logging
from google.cloud import spanner
from google.cloud.spanner_v1 import param_types

from services.cost_tracker import get_tracker

logger = logging.getLogger(__name__)

_client: spanner.Client | None = None
_database = None


def _is_demo_mode() -> bool:
    """True when DEMO_MODE=true or SPANNER_EMULATOR_HOST is set."""
    return (
        os.getenv("DEMO_MODE", "").lower() in ("1", "true", "yes")
        or bool(os.getenv("SPANNER_EMULATOR_HOST"))
    )


def get_database():
    """Get or create the Spanner database connection (lazy singleton).

    In DEMO_MODE / when SPANNER_EMULATOR_HOST is set, we connect to the local
    emulator with anonymous credentials and skip Model Armor / production auth.
    """
    global _client, _database
    if _database is None:
        project = os.getenv("SPANNER_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
        instance_id = os.getenv("SPANNER_INSTANCE", "kb-instance")
        database_id = os.getenv("SPANNER_DATABASE", "kb-db")

        if _is_demo_mode():
            from google.auth.credentials import AnonymousCredentials
            emulator_host = os.getenv("SPANNER_EMULATOR_HOST", "localhost:9010")
            logger.info(
                f"🧪 DEMO MODE: connecting to Spanner emulator at {emulator_host} "
                f"({project}/{instance_id}/{database_id})"
            )
            _client = spanner.Client(
                project=project or "demo-project",
                credentials=AnonymousCredentials(),
                client_options={"api_endpoint": emulator_host},
            )
        else:
            logger.info(f"Connecting to Spanner: {project}/{instance_id}/{database_id}")
            _client = spanner.Client(project=project)
        instance = _client.instance(instance_id)
        _database = instance.database(database_id)
    return _database


def run_query(sql: str, params: dict | None = None, param_types_map: dict | None = None) -> list[dict]:
    """Execute a read-only SQL query and return results as list of dicts.

    Args:
        sql: SQL query string with @param placeholders
        params: Dict of parameter values
        param_types_map: Dict of parameter types (spanner.param_types.*)

    Returns:
        List of row dicts with column names as keys
    """
    database = get_database()
    results = []

    with database.snapshot() as snapshot:
        result_set = snapshot.execute_sql(
            sql,
            params=params or {},
            param_types=param_types_map or {}
        )
        # Consume rows first (triggers metadata loading)
        rows = list(result_set)
        if result_set.fields:
            columns = [field.name for field in result_set.fields]
            results = [dict(zip(columns, row)) for row in rows]
        else:
            results = [{"col_" + str(i): v for i, v in enumerate(row)} for row in rows]

    return results


_MAX_ROWS_PER_BATCH = 2000  # Conservative: ~2K rows keeps commit under ~10MB with embeddings

# Interleave hierarchy: parent tables must be committed before children.
# Tier 0 = root, Tier 1 = interleaved in tier-0, Tier 2 = interleaved in tier-1.
_INTERLEAVE_TIER = {
    "Documents": 0,
    "DocumentChunks": 1,
    "DocumentMentions": 1,
    "ChunkMentions": 2,
}
# Entity / edge tables are standalone (tier 0)
_DEFAULT_TIER = 0


def batch_write(table_mutations: list[tuple[str, list[str], list[list]]]):
    """Execute a batch of insert_or_update mutations with interleave-aware splitting.

    Spanner limits:
    - 80,000 column-mutations per commit (1 row × N columns = N mutations)
    - ~10MB soft / 100MB hard per commit request
    - Interleaved child rows require parent rows to exist first

    This function groups mutations by interleave tier and writes parent tiers
    before children. Within each tier, rows are split into batches of
    _MAX_ROWS_PER_BATCH to stay well within size limits.

    Args:
        table_mutations: List of (table_name, columns, values_list) tuples.
            Each tuple represents one or more rows to upsert into a table.
            values_list is a list of row value lists.
    """
    database = get_database()

    # Group mutations by interleave tier
    tiers: dict[int, list[tuple[str, list[str], list]]] = {}
    total = 0
    for table_name, columns, values_list in table_mutations:
        tier = _INTERLEAVE_TIER.get(table_name, _DEFAULT_TIER)
        for values in values_list:
            tiers.setdefault(tier, []).append((table_name, columns, values))
            total += 1

    if total == 0:
        return

    # Write tiers in order: 0 (parents) → 1 → 2 (deepest children)
    written = 0
    for tier_num in sorted(tiers.keys()):
        tier_ops = tiers[tier_num]

        for start in range(0, len(tier_ops), _MAX_ROWS_PER_BATCH):
            chunk = tier_ops[start:start + _MAX_ROWS_PER_BATCH]
            try:
                with database.batch() as batch:
                    for table_name, columns, values in chunk:
                        batch.insert_or_update(
                            table=table_name,
                            columns=columns,
                            values=[values],
                        )
            except Exception as e:
                table_counts: dict[str, int] = {}
                for tbl, _, _ in chunk:
                    table_counts[tbl] = table_counts.get(tbl, 0) + 1
                logger.error(
                    f"Batch write failed tier={tier_num} offset={start} "
                    f"({len(chunk)} rows, {written}/{total} written so far): {e}\n"
                    f"  Tables in batch: {table_counts}"
                )
                # Diagnostic: retry per-table then per-row to find the culprit
                _diagnose_batch_failure(database, chunk)
                raise
            written += len(chunk)
            if total > _MAX_ROWS_PER_BATCH:
                logger.info(f"Batch written: tier={tier_num} {len(chunk)} rows ({written}/{total})")

    tracker = get_tracker()
    if tracker:
        tracker.track_spanner_write(mutations=total)

    logger.info(f"Batch write completed: {total} rows across {len(table_mutations)} table groups")


def _diagnose_batch_failure(database, chunk: list[tuple[str, list[str], list]]):
    """On batch failure, retry per-table then per-row to pinpoint the bad mutation."""
    # Group by table
    by_table: dict[str, list[tuple[str, list[str], list]]] = {}
    for tbl, cols, vals in chunk:
        by_table.setdefault(tbl, []).append((tbl, cols, vals))

    for table_name, ops in by_table.items():
        # Try writing all rows for this table alone
        try:
            with database.batch() as batch:
                for tbl, cols, vals in ops:
                    batch.insert_or_update(table=tbl, columns=cols, values=[vals])
            logger.info(f"  [diag] {table_name}: {len(ops)} rows OK")
        except Exception as table_err:
            logger.error(f"  [diag] {table_name}: FAILED ({len(ops)} rows): {table_err}")
            # Drill down: try each row individually
            for i, (tbl, cols, vals) in enumerate(ops):
                try:
                    with database.batch() as batch:
                        batch.insert_or_update(table=tbl, columns=cols, values=[vals])
                except Exception as row_err:
                    # Log the failing row's column names and truncated values
                    val_summary = []
                    for c, v in zip(cols, vals):
                        if isinstance(v, list):
                            val_summary.append(f"{c}=list[{len(v)}]")
                        elif isinstance(v, str) and len(v) > 80:
                            val_summary.append(f"{c}='{v[:80]}...'({len(v)}ch)")
                        else:
                            val_summary.append(f"{c}={v!r}")
                    logger.error(
                        f"  [diag] {table_name} row {i}: FAILED: {row_err}\n"
                        f"    {', '.join(val_summary)}"
                    )
                    return  # Found the culprit, stop
            logger.error(f"  [diag] {table_name}: all rows pass individually — likely duplicate PK in batch")


def is_connected() -> bool:
    """Check if the Spanner connection is healthy."""
    try:
        database = get_database()
        with database.snapshot() as snapshot:
            snapshot.execute_sql("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Spanner connection check failed: {e}")
        return False
