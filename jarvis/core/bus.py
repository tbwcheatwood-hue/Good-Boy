"""Async Event Bus — local pub/sub infrastructure.

Responsibilities:
- Decouples layers (L2 Speech publishes UtteranceCaptured, L3 Intent subscribes).
- Trace-ID-based correlation for debug replay.
- Delivers events to the flight recorder (when enabled).

Can be swapped for a Redis bus later when running multi-process.
"""
from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .events import Event

E = TypeVar("E", bound=Event)
Handler = Callable[[Event], Awaitable[None]]

# Hard cap on how long a *wildcard* subscriber (an observer/fan-out handler
# registered via ``subscribe_all`` -- WebSocket forwarders, channel adapters,
# recorders) may take before the bus abandons it for THIS dispatch.
#
# Rationale (BUG-CU-STALL, 2026-05-29 / AP-18): ``publish`` awaits every
# subscriber via ``asyncio.gather``. A wildcard observer that blocks -- e.g. a
# WebSocket ``send_json`` to a stalled/half-open browser tab, or a channel API
# call to a dead socket -- has NO natural bound and would freeze the *entire*
# event bus. Because the voice and Computer-Use dispatch paths publish through
# this bus (``ActionProposed``, ``HarnessDispatched``), one wedged browser tab
# silently froze a Computer-Use mission for ~28 s until the voice idle-timeout
# hung up -- "stood ready, did nothing". The module docstring of ``publish``
# already promised "a broken subscriber must never block the pipeline";
# this enforces it for the observer class that can actually block.
#
# Typed subscribers (``subscribe(EventType, ...)``) are deliberately NOT capped:
# a publisher may legitimately depend on them, and some (the TTS announcement
# handler) await audio playback for several seconds by design. The cap is
# generous enough that no healthy local observer is ever cut, yet far below the
# voice idle-timeout so a genuine wedge can never reach it.
_WILDCARD_HANDLER_TIMEOUT_S = 5.0
# publish() waits only this long. Handlers still running are left on the
# loop so a slow observer cannot stall the voice or inference publisher.
# Typed handlers are not cancelled: playback may outlive the publish call.
_PUBLISH_JOIN_S = 0.15


class EventBus:
    """In-process asyncio event bus with per-event-class topic subscriptions."""

    def __init__(self) -> None:
        self._subscribers: dict[type[Event], list[Handler]] = defaultdict(list)
        self._wildcard_subscribers: list[Handler] = []
        # subscribe() is synchronous and publish() is async, so an asyncio
        # lock cannot cover both. This lock is held only around the list
        # mutation and the snapshot copy, never across an await.
        self._handlers_lock = threading.Lock()
        self._detached: set[asyncio.Task[None]] = set()

    def subscribe(self, event_type: type[E], handler: Callable[[E], Awaitable[None]]) -> None:
        """Register a handler for a specific event type."""
        with self._handlers_lock:
            self._subscribers[event_type].append(handler)  # type: ignore[arg-type]

    def subscribe_all(self, handler: Handler) -> None:
        """Register a handler that receives EVERY event — e.g. flight recorder or metrics."""
        with self._handlers_lock:
            self._wildcard_subscribers.append(handler)

    def unsubscribe_all(self, handler: Handler) -> None:
        """Remove a wildcard handler registered via subscribe_all (no-op if absent).

        Symmetric to subscribe_all — short-lived wildcard observers (e.g. a
        WebSocket that lives only while a view is open) must be able to detach,
        or _wildcard_subscribers grows a dead handler per connect/disconnect."""
        with self._handlers_lock:
            if handler in self._wildcard_subscribers:
                self._wildcard_subscribers.remove(handler)

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], Awaitable[None]]) -> None:
        with self._handlers_lock:
            handlers = self._subscribers.get(event_type)
            if handlers and handler in handlers:  # type: ignore[operator]
                handlers.remove(handler)  # type: ignore[arg-type]

    async def publish(self, event: Event) -> None:
        """Deliver an event in parallel to all matching subscribers.

        Subscriber errors are logged but not propagated — a broken
        subscriber must never block the pipeline.
        """
        event_type = type(event)
        with self._handlers_lock:
            typed: list[Handler] = list(self._subscribers.get(event_type, []))
            wildcard: list[Handler] = list(self._wildcard_subscribers)
        if not typed and not wildcard:
            return

        # Each handler is its own task. publish returns once every handler
        # has finished or _PUBLISH_JOIN_S has passed, whichever comes first.
        # A subscriber that sleeps, logs, or waits on a socket cannot hold
        # the publisher. Wildcard handlers still time out. Typed handlers
        # keep running after the join so playback is not cut off.
        tasks = [
            asyncio.create_task(self._safe_dispatch(handler, event))
            for handler in typed
        ]
        tasks.extend(
            asyncio.create_task(
                self._safe_dispatch(
                    handler, event, timeout_s=_WILDCARD_HANDLER_TIMEOUT_S
                )
            )
            for handler in wildcard
        )
        _done, pending = await asyncio.wait(tasks, timeout=_PUBLISH_JOIN_S)
        for task in pending:
            self._detached.add(task)
            task.add_done_callback(self._detached.discard)

    @staticmethod
    async def _safe_dispatch(
        handler: Handler, event: Event, *, timeout_s: float | None = None
    ) -> None:
        try:
            if timeout_s is None:
                await handler(event)
            else:
                await asyncio.wait_for(handler(event), timeout=timeout_s)
        except TimeoutError:
            # A wildcard observer wedged (e.g. a WebSocket send to a stalled
            # browser tab). Abandon it for this dispatch — the bus must never
            # block on an observer (AP-18). Name the culprit so this is never
            # an invisible 28 s stall again.
            from loguru import logger

            logger.warning(
                "EventBus wildcard subscriber TIMED OUT (>{}s) and was "
                "abandoned — handler={} event={} (AP-18: an observer must "
                "never block the bus)",
                timeout_s,
                getattr(handler, "__qualname__", repr(handler)),
                type(event).__name__,
            )
        except Exception as exc:  # noqa: BLE001
            # Lazy import to avoid circular imports
            from loguru import logger

            logger.opt(exception=exc).warning(
                "EventBus subscriber failed",
                event=type(event).__name__,
                trace_id=str(event.trace_id),
            )


# Global default bus (usually overridden via DI/registry)
_default_bus: EventBus | None = None


def get_default_bus() -> EventBus:
    """Singleton accessor for cases where DI would have too much overhead."""
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus


def reset_default_bus() -> None:
    """For tests only."""
    global _default_bus
    _default_bus = None
