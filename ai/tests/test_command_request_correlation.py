import asyncio

from app.transport.protocol import Command
from app.transport.websocket.handler import RuntimeEventHandler


def test_management_response_echoes_request_id():
    handler = RuntimeEventHandler()
    responses = asyncio.run(
        handler.handle(Command(action="get_histories", params={}, request_id="request-42"))
    )
    assert responses
    assert responses[0].type == "command_response"
    assert responses[0].request_id == "request-42"
