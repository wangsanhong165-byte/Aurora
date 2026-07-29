import asyncio

from app.transport.websocket.handler import RuntimeEventHandler
from contracts.v3.registry import EventRegistry


def test_management_response_echoes_request_id():
    handler = RuntimeEventHandler()
    event = EventRegistry.parse({
        "protocolVersion": "3.0",
        "eventId": "event-command",
        "eventType": "management.requested",
        "sessionId": "session-1",
        "turnId": None,
        "sequence": 1,
        "source": "frontend",
        "timestamp": 1.0,
        "payload": {
            "action": "get_histories",
            "params": {},
            "requestId": "request-42",
        },
    })
    responses = asyncio.run(
        handler.handle_event(event)
    )
    assert responses
    assert responses[0].type == "command_response"
    assert responses[0].request_id == "request-42"
