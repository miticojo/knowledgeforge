"""In-process per-job event bus for streaming ingestion progress to SSE clients.

Design
------
- One ring buffer (deque, maxlen=500) per job_id holding the full event history.
- Subscribers receive a snapshot of buffered events first (replay), then tail
  live events via an ``asyncio.Queue``.
- Publishers are SYNCHRONOUS (called from FastAPI ``BackgroundTasks`` running
  on a worker thread). They mutate the ring buffer under a thread lock and
  fan out to subscriber queues using ``asyncio.run_coroutine_threadsafe`` so
  the queue ``put`` happens on the event loop the subscriber is iterating on.
- ``close(job_id)`` marks the stream terminal and unblocks all subscribers.

Limits
------
- 500 events per job (oldest evicted). Sufficient for repos in the low
  thousands of files (route + parse_start + parse_end ≈ 3 events/file).
- Memory only — events are lost on process restart. The poll-based status
  endpoint remains the source of truth for terminal state.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from itertools import count
from typing import AsyncIterator

logger = logging.getLogger(__name__)

MAX_EVENTS_PER_JOB = 500

# Sentinel pushed into a subscriber queue to signal "stream closed".
_CLOSE = object()


class _JobChannel:
    __slots__ = ("buffer", "subscribers", "closed", "lock", "seq")

    def __init__(self) -> None:
        self.buffer: deque[tuple[str, dict]] = deque(maxlen=MAX_EVENTS_PER_JOB)
        # list of (loop, queue) so publish() can schedule put on the right loop
        self.subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self.closed: bool = False
        self.lock = threading.Lock()
        self.seq = count()


_channels: dict[str, _JobChannel] = {}
_channels_lock = threading.Lock()


def _get_or_create(job_id: str) -> _JobChannel:
    with _channels_lock:
        ch = _channels.get(job_id)
        if ch is None:
            ch = _JobChannel()
            _channels[job_id] = ch
        return ch


def publish(job_id: str, event_type: str, data: dict) -> None:
    """Append an event to the job's ring buffer and fan out to subscribers.

    Thread-safe. Safe to call from a worker thread (FastAPI BackgroundTask).
    """
    ch = _get_or_create(job_id)
    enriched = {
        **data,
        "seq": next(ch.seq),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    payload = (event_type, enriched)
    with ch.lock:
        if ch.closed:
            # Tolerate late publishes (e.g. close() called before final event).
            logger.debug("publish on closed channel job_id=%s type=%s", job_id, event_type)
        ch.buffer.append(payload)
        subs = list(ch.subscribers)
    for loop, q in subs:
        try:
            asyncio.run_coroutine_threadsafe(q.put(payload), loop)
        except RuntimeError:
            # Loop closed; subscriber will be cleaned up on its next iteration.
            pass


def close(job_id: str) -> None:
    """Mark the channel terminal; in-flight subscribers get a close sentinel."""
    ch = _get_or_create(job_id)
    with ch.lock:
        if ch.closed:
            return
        ch.closed = True
        subs = list(ch.subscribers)
    for loop, q in subs:
        try:
            asyncio.run_coroutine_threadsafe(q.put(_CLOSE), loop)
        except RuntimeError:
            pass


async def subscribe(job_id: str) -> AsyncIterator[tuple[str, dict]]:
    """Yield buffered events first, then tail new ones until ``close()``.

    Must be awaited from an asyncio event loop. The subscriber is registered
    BEFORE the buffer snapshot is taken, so no event written between snapshot
    and registration is missed (the publisher will enqueue it on the queue).
    """
    ch = _get_or_create(job_id)
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    with ch.lock:
        ch.subscribers.append((loop, q))
        snapshot = list(ch.buffer)
        already_closed = ch.closed
    try:
        # Replay buffered events. We may double-deliver an event that arrived
        # between snapshot and registration: dedup via seq number.
        seen_seqs: set[int] = set()
        for evt in snapshot:
            seen_seqs.add(evt[1]["seq"])
            yield evt
        if already_closed:
            return
        while True:
            item = await q.get()
            if item is _CLOSE:
                return
            et, data = item  # type: ignore[misc]
            if data["seq"] in seen_seqs:
                continue
            yield (et, data)
    finally:
        with ch.lock:
            try:
                ch.subscribers.remove((loop, q))
            except ValueError:
                pass


def reset(job_id: str | None = None) -> None:
    """Test helper: drop one or all channels."""
    with _channels_lock:
        if job_id is None:
            _channels.clear()
        else:
            _channels.pop(job_id, None)


# Suppress "imported but unused" for time when linters strip the docstring.
_ = time
