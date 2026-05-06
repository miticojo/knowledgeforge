"""Tests for services.event_bus — in-process per-job event stream."""
from __future__ import annotations

import asyncio
import threading

import pytest

from services import event_bus


@pytest.fixture(autouse=True)
def _reset():
    event_bus.reset()
    yield
    event_bus.reset()


async def _drain(job_id: str, n: int, timeout: float = 2.0) -> list:
    """Pull up to n events from a fresh subscriber, then close it."""
    out: list = []
    agen = event_bus.subscribe(job_id).__aiter__()
    try:
        for _ in range(n):
            item = await asyncio.wait_for(agen.__anext__(), timeout=timeout)
            out.append(item)
    finally:
        await agen.aclose()
    return out


@pytest.mark.asyncio
async def test_publish_then_subscribe_replays_buffered_events():
    event_bus.publish("job1", "route", {"file": "a.py"})
    event_bus.publish("job1", "parse_end", {"file": "a.py", "entities_added": 3})
    event_bus.close("job1")

    events = []
    async for et, data in event_bus.subscribe("job1"):
        events.append((et, data["file"]))
    assert events == [("route", "a.py"), ("parse_end", "a.py")]
    # Each event has seq + ts
    # (re-subscribe to check enrichment)
    async for _, data in event_bus.subscribe("job1"):
        assert "seq" in data and "ts" in data


@pytest.mark.asyncio
async def test_two_subscribers_receive_same_live_events():
    event_bus.publish("job2", "route", {"file": "x.py"})

    a_events: list = []
    b_events: list = []
    a_started = asyncio.Event()
    b_started = asyncio.Event()

    async def collect(bag: list, started: asyncio.Event):
        agen = event_bus.subscribe("job2").__aiter__()
        try:
            # Drain replay (1 event), then signal ready and wait for live ones.
            first = await agen.__anext__()
            bag.append(first)
            started.set()
            while True:
                try:
                    item = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
                except (asyncio.TimeoutError, StopAsyncIteration):
                    return
                bag.append(item)
        finally:
            await agen.aclose()

    ta = asyncio.create_task(collect(a_events, a_started))
    tb = asyncio.create_task(collect(b_events, b_started))
    await a_started.wait()
    await b_started.wait()

    # Publish from another thread to mirror BackgroundTask behavior.
    def publisher():
        event_bus.publish("job2", "parse_end", {"file": "x.py"})
        event_bus.close("job2")

    threading.Thread(target=publisher).start()
    await asyncio.gather(ta, tb)

    assert [et for et, _ in a_events] == ["route", "parse_end"]
    assert [et for et, _ in b_events] == ["route", "parse_end"]


@pytest.mark.asyncio
async def test_buffer_evicts_oldest_past_max():
    cap = event_bus.MAX_EVENTS_PER_JOB
    for i in range(cap + 50):
        event_bus.publish("jobcap", "tick", {"i": i})
    event_bus.close("jobcap")

    seen = []
    async for _, data in event_bus.subscribe("jobcap"):
        seen.append(data["i"])
    assert len(seen) == cap
    # Oldest 50 evicted; first remaining should be i=50.
    assert seen[0] == 50
    assert seen[-1] == cap + 49


@pytest.mark.asyncio
async def test_close_ends_iterator():
    event_bus.publish("jobclose", "route", {"file": "a"})

    agen = event_bus.subscribe("jobclose").__aiter__()
    first = await agen.__anext__()
    assert first[0] == "route"

    # Close from another thread; the iterator must terminate.
    threading.Thread(target=event_bus.close, args=("jobclose",)).start()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(agen.__anext__(), timeout=2.0)
    await agen.aclose()
