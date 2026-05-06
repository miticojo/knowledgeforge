"""Per-job on-disk store for raw uploaded bytes (e.g. PDF originals).

The text-based artifact_store keeps extracted text + parsed entities in memory
for the Live Inspector. For binary originals (PDF) we want the frontend to be
able to render the *real* file via `<embed>`, which means we need the bytes.

Design
------
- Bytes are written to a tempdir keyed by job_id (one dir per job, one file
  per ingested document). We do not buffer them in memory: a 50 MB PDF would
  blow the SSE event-loop heap if held alongside the artifact_store entry.
- TTL is the same shape as services.artifact_store: `mark_closed(job_id)`
  starts the clock and `gc()` (called opportunistically on every put/get)
  removes job dirs older than `TTL_SECONDS`.
- This store does NOT track the path -> bytes mapping itself; it returns a
  filesystem path per (job_id, doc_path) and the caller can stream from it.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

TTL_SECONDS = 30 * 60
_ROOT: Path | None = None
_lock = threading.Lock()
# job_id -> {"dir": Path, "closed_at": float | None, "files": dict[str, Path]}
_jobs: dict[str, dict] = {}


def _root() -> Path:
    global _ROOT
    if _ROOT is None:
        _ROOT = Path(tempfile.mkdtemp(prefix="kf-raw-artifacts-"))
    return _ROOT


def _safe_name(path: str) -> str:
    """Map an arbitrary doc path to a filesystem-safe basename.

    The caller path is user-controlled (uploaded filename, possibly with
    slashes) so we hash it. The original is preserved as a side metadata
    field on the artifact_store entry; this store only needs to round-trip
    the bytes, so a hash is enough.
    """
    h = hashlib.sha1(path.encode("utf-8", errors="replace")).hexdigest()[:16]
    suffix = Path(path).suffix
    return f"{h}{suffix}"


def put(job_id: str, doc_path: str, data: bytes) -> Path:
    """Write `data` for (job_id, doc_path) and return the on-disk path."""
    with _lock:
        _gc_locked()
        job = _jobs.get(job_id)
        if job is None:
            jdir = _root() / job_id
            jdir.mkdir(parents=True, exist_ok=True)
            job = {"dir": jdir, "closed_at": None, "files": {}}
            _jobs[job_id] = job
        fp = job["dir"] / _safe_name(doc_path)
        fp.write_bytes(data)
        job["files"][doc_path] = fp
        return fp


def get_path(job_id: str, doc_path: str) -> Path | None:
    with _lock:
        _gc_locked()
        job = _jobs.get(job_id)
        if job is None:
            return None
        fp = job["files"].get(doc_path)
        return fp if fp and fp.exists() else None


def mark_closed(job_id: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job["closed_at"] = time.time()


def _gc_locked() -> None:
    now = time.time()
    drop: list[str] = []
    for jid, job in _jobs.items():
        ca = job.get("closed_at")
        if ca is not None and (now - ca) > TTL_SECONDS:
            drop.append(jid)
    for jid in drop:
        job = _jobs.pop(jid, None)
        if job is not None:
            try:
                shutil.rmtree(job["dir"], ignore_errors=True)
            except Exception:
                pass


def _reset_for_tests() -> None:
    with _lock:
        for job in _jobs.values():
            try:
                shutil.rmtree(job["dir"], ignore_errors=True)
            except Exception:
                pass
        _jobs.clear()
