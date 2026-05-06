"""Per-job in-memory artifact store for the M3 Live Inspector.

Holds the raw source, parser output, and ArchiMate entities/edges produced for
each ingested file so the frontend can pull a per-file detail view without a
second round-trip to the parser.

Lifecycle
---------
- Writers (the GitIngester background task) call `put(job_id, file, payload)`.
- Readers (the FastAPI handler for /ingest/git/{job_id}/file) call `get`.
- When a job finishes, the runner calls `mark_closed(job_id)` to start the
  TTL clock; entries are GC'd after `TTL_SECONDS`.
- `gc()` is invoked opportunistically on every `put`/`get` so we never need
  a background sweeper thread.

Bounds
------
- At most `MAX_FILES_PER_JOB` files are retained per job (subsequent puts are
  dropped silently — the SSE stream is the source of truth for "all files",
  the inspector is best-effort).
- Source is truncated to `MAX_SOURCE_BYTES` with a `...truncated...` suffix.

Thread safety
-------------
A single `threading.Lock` guards the whole structure. All operations are
short (dict ops, no I/O), so contention is negligible.
"""
from __future__ import annotations

import threading
import time
from typing import Any

MAX_FILES_PER_JOB = 500
MAX_SOURCE_BYTES = 50 * 1024
TTL_SECONDS = 30 * 60  # 30 minutes after job close


def _truncate_source(src: str) -> str:
    if src is None:
        return ""
    if len(src.encode("utf-8", errors="replace")) <= MAX_SOURCE_BYTES:
        return src
    # Truncate by characters approximating the byte budget; cheap and good
    # enough for source code.
    return src[:MAX_SOURCE_BYTES] + "\n...truncated..."


class _ArtifactStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # job_id -> {"files": {rel_path: payload}, "closed_at": float | None}
        self._jobs: dict[str, dict[str, Any]] = {}

    # --------------------------------------------------------------- writers
    def put(self, job_id: str, file_path: str, payload: dict) -> None:
        """Store the per-file artifact. Truncates source. Drops if at cap."""
        normalized = dict(payload)
        if "source" in normalized:
            normalized["source"] = _truncate_source(normalized.get("source") or "")
        with self._lock:
            self._gc_locked()
            job = self._jobs.setdefault(job_id, {"files": {}, "closed_at": None})
            files = job["files"]
            if file_path in files or len(files) < MAX_FILES_PER_JOB:
                files[file_path] = normalized

    def mark_closed(self, job_id: str) -> None:
        """Start the TTL clock for `job_id`. Idempotent."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job["closed_at"] = time.time()

    # --------------------------------------------------------------- readers
    def get(self, job_id: str, file_path: str) -> dict | None:
        with self._lock:
            self._gc_locked()
            job = self._jobs.get(job_id)
            if job is None:
                return None
            payload = job["files"].get(file_path)
            return dict(payload) if payload is not None else None

    def list_files(self, job_id: str) -> list[str]:
        with self._lock:
            job = self._jobs.get(job_id)
            return list(job["files"].keys()) if job else []

    # ---------------------------------------------------- internal: eviction
    def _gc_locked(self) -> None:
        now = time.time()
        to_drop = []
        for jid, job in self._jobs.items():
            closed_at = job.get("closed_at")
            if closed_at is not None and (now - closed_at) > TTL_SECONDS:
                to_drop.append(jid)
        for jid in to_drop:
            self._jobs.pop(jid, None)

    # --------------------------------------------------------------- testing
    def _reset_for_tests(self) -> None:
        with self._lock:
            self._jobs.clear()


# Module-level singleton.
store = _ArtifactStore()
