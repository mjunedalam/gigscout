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
    workspace_id: int | None = None  # who may see it; None means every workspace

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "at": self.at, "data": self.data}


@dataclass(frozen=True)
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue
    workspace_id: int | None = None


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[_Subscriber] = set()
        self._recent: deque[Event] = deque(maxlen=RECENT_EVENTS)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def publish(self, type_: str, data: dict[str, Any] | None = None, workspace_id: int | None = None) -> Event:
        event = Event(id=next(self._ids), type=type_, at=datetime.now(UTC).isoformat(), data=data or {},
                      workspace_id=workspace_id)
        with self._lock:
            if not type_.startswith("metrics.") and type_ not in QUIET_TYPES:  # these would flood the activity history
                self._recent.append(event)
            subscribers = [s for s in self._subscribers if _sees(s.workspace_id, event)]
        for sub in subscribers:
            try:
                sub.loop.call_soon_threadsafe(_offer, sub.queue, event)
            except RuntimeError:  # loop already closed: the client went away
                self.unsubscribe(sub)
        return event

    def subscribe(self, workspace_id: int | None = None) -> _Subscriber:
        sub = _Subscriber(loop=asyncio.get_running_loop(), queue=asyncio.Queue(maxsize=QUEUE_SIZE),
                          workspace_id=workspace_id)
        with self._lock:
            self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        with self._lock:
            self._subscribers.discard(sub)

    def recent(self, limit: int = 50, workspace_id: int | None = None) -> list[Event]:
        with self._lock:
            visible = [e for e in self._recent if _sees(workspace_id, e)]
        return visible[-limit:][::-1]

    def watched_workspaces(self) -> set[int]:
        with self._lock:
            return {s.workspace_id for s in self._subscribers if s.workspace_id is not None}

    def subscribers_in(self, workspace_id: int) -> int:
        with self._lock:
            return sum(1 for s in self._subscribers if s.workspace_id == workspace_id)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


def _sees(workspace_id: int | None, event: Event) -> bool:
    return event.workspace_id is None or workspace_id is None or event.workspace_id == workspace_id


def _offer(queue: asyncio.Queue, event: Event) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        log.debug("Dropping event %s for a slow subscriber", event.id)
