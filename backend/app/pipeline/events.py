"""In-process progress events per job (the CLI prints them; Phase 6 streams them over SSE).

Event types (prompt.md §6.6): stage, scene, stream_ready, completed, failed.
"""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from app.models.job import now


@dataclass
class Event:
    job_id: str
    type: str
    data: dict
    at: str = field(default_factory=lambda: now().isoformat())


TERMINAL = ("completed", "failed")


class Subscription:
    """Events for one job, queued from the moment it was opened."""

    def __init__(self, bus: "EventBus", job_id: str):
        self._bus, self.job_id = bus, job_id
        self._queue: asyncio.Queue = asyncio.Queue()

    def put(self, event: Event) -> None:
        self._queue.put_nowait(event)

    async def get(self, timeout: float | None = None) -> Event | None:
        """The next event, or None if nothing arrived within `timeout` seconds."""
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except TimeoutError:
            return None

    def close(self) -> None:
        self._bus._subs[self.job_id].discard(self)


class EventBus:
    def __init__(self):
        self._subs: dict[str, set[Subscription]] = defaultdict(set)
        self._listeners: list[Callable[[Event], None]] = []

    def listen(self, callback: Callable[[Event], None]) -> None:
        """Call `callback` synchronously for every event of every job."""
        self._listeners.append(callback)

    def publish(self, job_id, type: str, **data) -> Event:
        event = Event(str(job_id), type, data)
        for callback in self._listeners:
            callback(event)
        for sub in list(self._subs.get(event.job_id, ())):
            sub.put(event)
        return event

    def open(self, job_id) -> Subscription:
        """Start queueing this job's events now (synchronously, so none are missed)."""
        sub = Subscription(self, str(job_id))
        self._subs[str(job_id)].add(sub)
        return sub

    async def subscribe(self, job_id) -> AsyncIterator[Event]:
        """Events for one job until it completes or fails."""
        sub = self.open(job_id)
        try:
            while True:
                event = await sub.get()
                yield event
                if event.type in TERMINAL:
                    return
        finally:
            sub.close()
