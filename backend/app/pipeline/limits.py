"""Bounded concurrency where the lowest priority number goes first (scene 1 before scene 2).

Renders also keep one slot for the "front" scene (the earliest one not rendered yet): the live
stream can only start, and only grows, from that scene, so later scenes must never take every
slot while it is still getting ready (e.g. while its icon is being drawn).
"""

import asyncio
import itertools
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


@dataclass(order=True)
class _Waiter:
    priority: int
    order: int
    is_front: Callable[[], bool] | None = field(compare=False)
    future: asyncio.Future = field(compare=False)


class PrioritySemaphore:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self.active = 0
        self.active_others = 0  # slots held by holders that were not the front scene
        self._waiters: list[_Waiter] = []
        self._order = itertools.count()  # ties keep arrival order

    def _kind(self, is_front: Callable[[], bool] | None) -> str | None:
        """'front' or 'other' if a slot can be granted now, else None."""
        if self.active >= self.capacity:
            return None
        if is_front is None or is_front():
            return "front"
        # Non-front holders may use every slot but one (when there is more than one).
        reserve = 1 if self.capacity > 1 else 0
        return "other" if self.active_others < self.capacity - reserve else None

    def _take(self, kind: str) -> str:
        self.active += 1
        if kind == "other":
            self.active_others += 1
        return kind

    def _wake_next(self) -> None:
        for waiter in sorted(self._waiters):
            if waiter.future.done():
                self._waiters.remove(waiter)
                continue
            kind = self._kind(waiter.is_front)
            if kind is not None:
                self._waiters.remove(waiter)
                waiter.future.set_result(self._take(kind))

    async def acquire(
        self, priority: int, is_front: Callable[[], bool] | None = None
    ) -> str:
        """Returns the kind of slot taken ('front' or 'other'); pass it back to release()."""
        future = asyncio.get_running_loop().create_future()
        self._waiters.append(_Waiter(priority, next(self._order), is_front, future))
        # Grant at once if it may run now (e.g. the front scene arrives while others wait).
        self._wake_next()
        try:
            return await future
        except asyncio.CancelledError:
            if future.done() and not future.cancelled():
                # Granted just as we were cancelled: hand the slot on.
                self.release(future.result())
            raise

    def release(self, kind: str = "front") -> None:
        self.active -= 1
        if kind == "other":
            self.active_others -= 1
        self._wake_next()

    def notify(self) -> None:
        """Re-check waiters (e.g. after which scene is the front one changed)."""
        self._wake_next()

    @asynccontextmanager
    async def slot(
        self, priority: int, is_front: Callable[[], bool] | None = None
    ) -> AsyncIterator[None]:
        kind = await self.acquire(priority, is_front)
        try:
            yield
        finally:
            self.release(kind)
