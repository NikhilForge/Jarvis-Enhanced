"""Tiny async event bus: every subsystem publishes trace events, the HUD subscribes."""
import asyncio, time
from typing import Any, Dict, List, Tuple


class EventBus:
    def __init__(self) -> None:
        self._subs: List[Tuple[asyncio.Queue, asyncio.AbstractEventLoop]] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        self._subs.append((q, loop))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs = [(sq, loop) for sq, loop in self._subs if sq != q]

    def _put(self, q: asyncio.Queue, evt: Any) -> None:
        try:
            q.put_nowait(evt)
        except asyncio.QueueFull:
            pass

    def emit(self, channel: str, text: str, **extra: Any) -> None:
        evt: Dict[str, Any] = {"ts": time.time(), "channel": channel, "text": text, **extra}
        for q, loop in list(self._subs):
            try:
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(self._put, q, evt)
                else:
                    self._put(q, evt)
            except Exception:
                pass


BUS = EventBus()
