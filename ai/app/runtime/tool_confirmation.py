"""In-process confirmation broker for side-effecting tool calls."""

from __future__ import annotations

import asyncio
from uuid import uuid4


class ToolConfirmationBroker:
    def __init__(self):
        self._pending: dict[str, asyncio.Future[bool]] = {}

    async def request(self, notify, tool: str, args: dict, risk: str) -> bool:
        request_id = uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending[request_id] = future
        try:
            await notify({
                "request_id": request_id,
                "tool": tool,
                "args": args,
                "risk": risk,
            })
            return await asyncio.wait_for(future, timeout=120)
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending.pop(request_id, None)

    def resolve(self, request_id: str, approved: bool) -> bool:
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(bool(approved))
        return True


tool_confirmation_broker = ToolConfirmationBroker()
