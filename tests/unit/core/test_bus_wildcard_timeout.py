"""Regression guard for BUG-CU-STALL / AP-18: a wedged wildcard (observer)
subscriber must never block ``EventBus.publish`` — which would freeze the
voice and Computer-Use dispatch paths that publish through the bus.

The original failure: the WebSocket fan-out forwarder (a ``subscribe_all``
handler) awaited ``ws.send_json`` to a stalled/half-open browser tab with no
timeout. ``publish`` awaits every subscriber via ``asyncio.gather``, so one
wedged tab silently froze the whole bus for ~28 s until the voice idle-timeout
hung up — "stood ready, did nothing".
"""
from __future__ import annotations

import asyncio

import pytest

from jarvis.core import bus as bus_mod
from jarvis.core.bus import EventBus
from jarvis.core.events import Event


@pytest.mark.asyncio
async def test_wedged_wildcard_subscriber_does_not_block_publish(monkeypatch):
    # Tiny timeout so the test is fast; publish must return ~immediately after.
    monkeypatch.setattr(bus_mod, "_WILDCARD_HANDLER_TIMEOUT_S", 0.05)
    bus = EventBus()

    typed_seen: list[Event] = []
    wildcard_started = asyncio.Event()

    async def fast_typed(event: Event) -> None:
        typed_seen.append(event)

    async def wedged_wildcard(event: Event) -> None:
        wildcard_started.set()
        await asyncio.sleep(3600)  # simulate a stalled WS send

    bus.subscribe(Event, fast_typed)
    bus.subscribe_all(wedged_wildcard)

    # Must complete well within the wedge duration — bounded by the timeout,
    # not by the 3600 s sleep.
    await asyncio.wait_for(bus.publish(Event()), timeout=1.0)

    assert wildcard_started.is_set()      # the wildcard handler did run
    assert len(typed_seen) == 1           # the fast typed handler still got the event


@pytest.mark.asyncio
async def test_typed_subscriber_is_not_cancelled_when_publish_returns(monkeypatch):
    # Playback handlers may outlive publish. publish must return without
    # waiting them out, and it must not cancel them.
    monkeypatch.setattr(bus_mod, "_PUBLISH_JOIN_S", 0.05)
    bus = EventBus()
    completed = asyncio.Event()

    async def slow_typed(event: Event) -> None:
        await asyncio.sleep(0.2)
        completed.set()

    bus.subscribe(Event, slow_typed)
    await asyncio.wait_for(bus.publish(Event()), timeout=0.5)
    assert not completed.is_set()
    await asyncio.wait_for(completed.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_stalled_subscriber_does_not_delay_healthy_ones(monkeypatch):
    monkeypatch.setattr(bus_mod, "_PUBLISH_JOIN_S", 0.05)
    bus = EventBus()
    seen: list[str] = []

    async def stalled(event: Event) -> None:
        await asyncio.sleep(2.0)

    async def healthy(event: Event) -> None:
        seen.append(type(event).__name__)

    bus.subscribe(Event, stalled)
    bus.subscribe(Event, healthy)
    started = asyncio.get_event_loop().time()
    await bus.publish(Event())
    elapsed = asyncio.get_event_loop().time() - started
    assert elapsed < 0.5
    assert seen == ["Event"]


@pytest.mark.asyncio
async def test_raising_wildcard_subscriber_is_swallowed():
    bus = EventBus()
    other_seen: list[Event] = []

    async def boom(event: Event) -> None:
        raise RuntimeError("subscriber blew up")

    async def healthy(event: Event) -> None:
        other_seen.append(event)

    bus.subscribe_all(boom)
    bus.subscribe_all(healthy)

    # Must not propagate; the healthy sibling still receives the event.
    await bus.publish(Event())
    assert len(other_seen) == 1
