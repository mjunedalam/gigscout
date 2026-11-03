"""In-process event bus feeding the live UI over Server-Sent Events.

Publishers may be worker threads (runs, scheduler) or request handlers; subscribers are asyncio SSE streams.
Each subscriber gets a bounded queue, and a slow subscriber drops events instead of slowing publishers down.
"""

import asyncio
import itertools
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

QUEUE_SIZE = 500
RECENT_EVENTS = 200
QUIET_TYPES = {"run.activity"}  # high-volume, streamed live but not kept in recent history


@dataclass(frozen=True)
class Event:
    id: int
    type: str
    at: str
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "at": self.at, "data": self.data}


@dataclass(frozen=True)
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[_Subscriber] = set()
        self._recent: deque[Event] = deque(maxlen=RECENT_EVENTS)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def publish(self, type_: str, data: dict[str, Any] | None = None) -> Event:
        event = Event(id=next(self._ids), type=type_, at=datetime.now(UTC).isoformat(), data=data or {})
        with self._lock:
            if not type_.startswith("metrics.") and type_ not in QUIET_TYPES:  # these would flood the activity history
                self._recent.append(event)
            subscribers = list(self._subscribers)
        for sub in subscribers:
            try:
                sub.loop.call_soon_threadsafe(_offer, sub.queue, event)
            except RuntimeError:  # loop already closed: the client went away
                self.unsubscribe(sub)
        return event

    def subscribe(self) -> _Subscriber:
        sub = _Subscriber(loop=asyncio.get_running_loop(), queue=asyncio.Queue(maxsize=QUEUE_SIZE))
        with self._lock:
            self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        with self._lock:
            self._subscribers.discard(sub)

    def recent(self, limit: int = 50) -> list[Event]:
        with self._lock:
            return list(self._recent)[-limit:][::-1]

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


def _offer(queue: asyncio.Queue, event: Event) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        log.debug("Dropping event %s for a slow subscriber", event.id)
