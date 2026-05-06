"""Initialize the Spanner emulator for KnowledgeForge demo.

Idempotent. Reads connection details from environment:
    SPANNER_EMULATOR_HOST  (default localhost:9010)
    SPANNER_PROJECT        (default demo-project)
    SPANNER_INSTANCE       (default demo-instance)
    SPANNER_DATABASE       (default demo-db)

Steps:
  1. Connect to the emulator with anonymous credentials.
  2. Create instance if absent.
  3. Create database if absent and apply DDL files in production order:
        a. database/spanner_schema.sdl       (base schema)
        b. database/migrations/*.sql         (alphabetical)
        c. database/add_tenant_id.ddl        (tenant migration last)
     Statements that the emulator does not support (CREATE MODEL — Vertex AI
     remote models, CREATE VECTOR INDEX) are filtered out and reported.

Each statement is applied individually so duplicate-column / already-exists
errors can be caught and ignored, allowing re-runs against an already-
initialised emulator to succeed.

Exit 0 on success, non-zero on hard failure.
"""
from __future__ import annotations

import os
import re
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[init_emulator] %(message)s")
log = logging.getLogger(__name__)


# Substrings (case-insensitive) that mark a benign duplicate / already-applied
# DDL error from Spanner / the emulator. If the error message contains any of
# these tokens, we log "skipped-duplicate" and continue.
_DUPLICATE_TOKENS = (
    "duplicate column",
    "already exists",
    "duplicate name",
    "is already",
    "column already exists",
    # Spanner emulator rejects ALTER on key columns even when the target type
    # already matches (base schema declares doc_id STRING(MAX); migration 002
    # tries to widen it again — a no-op we treat as benign).
    "could not be made",
    "cannot alter parent key column",
)


def _split_ddl(sdl_text: str) -> list[str]:
    """Split a DDL text blob into individual statements.

    Strips line comments (-- ...) and blank statements, then splits on top-
    level ';'. CREATE MODEL and CREATE VECTOR INDEX blocks are dropped because
    the emulator does not support them.
    """
    cleaned = "\n".join(
        re.sub(r"--.*$", "", line) for line in sdl_text.splitlines()
    )
    raw_stmts = [s.strip() for s in cleaned.split(";")]
    stmts: list[str] = []
    skipped: list[str] = []
    for s in raw_stmts:
        if not s:
            continue
        head = s.lstrip().upper()
        if head.startswith("CREATE MODEL") or head.startswith("CREATE OR REPLACE MODEL"):
            name_match = re.search(r"MODEL\s+(\w+)", s, re.IGNORECASE)
            skipped.append(f"MODEL:{name_match.group(1) if name_match else '?'}")
            continue
        if "CREATE VECTOR INDEX" in head or "CREATE OR REPLACE VECTOR INDEX" in head:
            name_match = re.search(r"VECTOR\s+INDEX\s+(\w+)", s, re.IGNORECASE)
            skipped.append(f"VECTOR_INDEX:{name_match.group(1) if name_match else '?'}")
            continue
        stmts.append(s)
    if skipped:
        log.info(
            f"Filtered {len(skipped)} unsupported stmts (emulator): {skipped}"
        )
    return stmts


def _is_duplicate_error(err: Exception) -> bool:
    msg = str(err).lower()
    return any(tok in msg for tok in _DUPLICATE_TOKENS)


def _stmt_preview(stmt: str, n: int = 80) -> str:
    flat = " ".join(stmt.split())
    return flat[:n] + ("..." if len(flat) > n else "")


def _apply_statements(database, file_label: str, stmts: list[str]) -> tuple[int, int, int]:
    """Apply DDL statements one-by-one. Returns (applied, skipped, errors).

    Duplicate / already-exists errors are logged and ignored so the run can
    proceed. Any other error is re-raised after logging the failing statement.
    """
    applied = skipped = errors = 0
    for i, stmt in enumerate(stmts, start=1):
        preview = _stmt_preview(stmt)
        try:
            op = database.update_ddl([stmt])
            op.result(timeout=120)
            applied += 1
            log.info(f"  [{file_label} {i}/{len(stmts)}] applied        — {preview}")
        except Exception as e:  # noqa: BLE001 — we classify below
            if _is_duplicate_error(e):
                skipped += 1
                log.info(f"  [{file_label} {i}/{len(stmts)}] skipped-dup    — {preview}")
            else:
                errors += 1
                log.error(f"  [{file_label} {i}/{len(stmts)}] ERROR          — {preview}")
                log.error(f"    -> {e}")
                raise
    log.info(
        f"  {file_label}: applied={applied} skipped-duplicate={skipped} errors={errors}"
    )
    return applied, skipped, errors


def _collect_ddl_files(database_dir: Path) -> list[tuple[str, Path]]:
    """Return ordered list of (label, path) for DDL application."""
    files: list[tuple[str, Path]] = []
    schema = database_dir / "spanner_schema.sdl"
    if schema.exists():
        files.append(("schema", schema))
    migrations_dir = database_dir / "migrations"
    if migrations_dir.is_dir():
        for sql_path in sorted(migrations_dir.glob("*.sql")):
            files.append((f"migration:{sql_path.name}", sql_path))
    tenant = database_dir / "add_tenant_id.ddl"
    if tenant.exists():
        files.append(("tenant", tenant))
    cost_log = database_dir / "add_cost_log.ddl"
    if cost_log.exists():
        files.append(("cost_log", cost_log))
    return files


def main() -> int:
    project = os.getenv("SPANNER_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or "demo-project"
    instance_id = os.getenv("SPANNER_INSTANCE", "demo-instance")
    database_id = os.getenv("SPANNER_DATABASE", "demo-db")
    emulator_host = os.getenv("SPANNER_EMULATOR_HOST", "localhost:9010")

    # Force emulator path for this script.
    os.environ["SPANNER_EMULATOR_HOST"] = emulator_host

    database_dir = Path(__file__).resolve().parents[2] / "database"
    schema_path = database_dir / "spanner_schema.sdl"
    if not schema_path.exists():
        log.error(f"Schema not found at {schema_path}")
        return 2

    ddl_files = _collect_ddl_files(database_dir)
    log.info(f"Emulator     = {emulator_host}")
    log.info(f"Project      = {project}")
    log.info(f"Instance     = {instance_id}")
    log.info(f"Database     = {database_id}")
    log.info(f"DDL files    = {[label for label, _ in ddl_files]}")

    try:
        from google.cloud import spanner
        from google.auth.credentials import AnonymousCredentials
    except ImportError as e:
        log.error(f"google-cloud-spanner not installed: {e}")
        return 3

    client = spanner.Client(
        project=project,
        credentials=AnonymousCredentials(),
        client_options={"api_endpoint": emulator_host},
    )

    # Step 1 — instance
    instance = client.instance(instance_id)
    if not instance.exists():
        log.info(f"Creating instance {instance_id} ...")
        instance = client.instance(
            instance_id,
            configuration_name=f"projects/{project}/instanceConfigs/emulator-config",
            display_name="KF Demo Instance",
            node_count=1,
        )
        op = instance.create()
        op.result(timeout=60)
        log.info("Instance created.")
    else:
        log.info("Instance already exists.")

    # Step 2 — database (create empty if absent — schema applied below)
    database = instance.database(database_id)
    if not database.exists():
        log.info(f"Creating empty database {database_id} ...")
        op = database.create()
        op.result(timeout=300)
        log.info("Database created.")
    else:
        log.info("Database already exists.")

    # Step 3 — apply each DDL file in order, statement-by-statement
    totals = {"applied": 0, "skipped": 0, "errors": 0}
    for label, path in ddl_files:
        log.info(f"Applying {label} <- {path.name}")
        stmts = _split_ddl(path.read_text())
        if not stmts:
            log.info(f"  {label}: no statements after filtering, skipping")
            continue
        applied, skipped, errors = _apply_statements(database, label, stmts)
        totals["applied"] += applied
        totals["skipped"] += skipped
        totals["errors"] += errors

    log.info(
        f"Done. Totals: applied={totals['applied']} "
        f"skipped-duplicate={totals['skipped']} errors={totals['errors']}"
    )
    log.info("Emulator init complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
