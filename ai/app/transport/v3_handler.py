"""V3 RuntimeEvent handler port.

Kept as a small named boundary so transports depend on a V3 callable rather
than on RuntimeEventHandler implementation details.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from contracts.v3.envelope import EventEnvelope


RuntimeEventCallback = Callable[
    [EventEnvelope],
    Awaitable[list[EventEnvelope | object] | None],
]


class V3EventHandler:
    def __init__(self, handler: RuntimeEventCallback):
        self._handler = handler

    async def handle(self, event: EventEnvelope) -> list[EventEnvelope | object]:
        return await self._handler(event) or []
