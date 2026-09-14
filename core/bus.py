"""Tiny async event bus: every subsystem publishes trace events, the HUD subscribes."""
import asyncio, time
from typing import Any, Dict, List


class EventBus:
    def __init__(self) -> None:
        self._subs: List[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subs:
            self._subs.remove(q)

    def emit(self, channel: str, text: str, **extra: Any) -> None:
        evt: Dict[str, Any] = {"ts": time.time(), "channel": channel, "text": text, **extra}
        for q in list(self._subs):
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                pass


BUS = EventBus()
