import asyncio
import json
from pathlib import Path

from app.bridge.server import app
from app.transport.session import WebSocketSession


ROOT = Path(__file__).resolve().parents[1]


class _Disconnect(Exception):
    pass


class _WebSocketProbe:
    def __init__(self):
        self.messages: list[dict] = []
        self.incoming = [json.dumps({
            "protocolVersion": "3.0",
            "eventId": "event-open",
            "eventType": "session.open",
            "sessionId": "session-test",
            "turnId": None,
            "sequence": 1,
            "source": "frontend",
            "timestamp": 1.0,
            "payload": {"capabilities": ["text"]},
        })]

    async def accept(self):
        return None

    async def send_text(self, payload: str):
        self.messages.append(json.loads(payload))

    async def receive_text(self):
        if self.incoming:
            return self.incoming.pop(0)
        from fastapi import WebSocketDisconnect

        raise WebSocketDisconnect()


def test_client_ws_is_the_only_production_websocket_route():
    routes = {
        route.path
        for route in app.routes
        if route.__class__.__name__ == "APIWebSocketRoute"
    }

    assert routes == {"/client-ws"}


def test_session_announces_transport_protocol_v3():
    websocket = _WebSocketProbe()

    async def handler(_message):
        return None

    asyncio.run(WebSocketSession(websocket, handler).run())

    init = websocket.messages[0]
    assert init["protocolVersion"] == "3.0"
    assert init["eventType"] == "session.opened"
    assert init["sessionId"]
    assert init["turnId"] is None
    assert init["payload"]["capabilities"]


def test_production_runtime_has_no_legacy_turn_entrypoint():
    runtime_source = (ROOT / "app" / "runtime" / "runtime.py").read_text("utf-8")
    server_source = (ROOT / "app" / "bridge" / "server.py").read_text("utf-8")

    assert "def dispatch(" not in runtime_source
    assert "def dispatch(" not in server_source
    assert "CompanionRuntime" not in runtime_source
    assert "CompanionRuntime" not in server_source


def test_core_runtime_tests_do_not_recreate_legacy_dispatch():
    sources = [
        (ROOT / "tests" / "test_runtime_pipeline.py").read_text("utf-8"),
        (ROOT / "tests" / "turn_input_fixtures.py").read_text("utf-8"),
        (ROOT / "tests" / "test_production_regressions.py").read_text("utf-8"),
    ]
    combined = "\n".join(sources)

    assert "class CompanionRuntime" not in combined
    assert "EventFixtureRuntime" not in combined
    assert ".dispatch(" not in combined
    assert ".dispatch_fixture(" not in combined


def test_frontend_connects_only_to_canonical_client_ws():
    app_source = (
        ROOT / "frontend" / "src" / "session" / "DesktopSessionProvider.tsx"
    ).read_text("utf-8")
    client_source = (
        ROOT / "frontend" / "src" / "runtime" / "client.ts"
    ).read_text("utf-8")
    assert "runtimeWebSocketUrl(location)" in app_source
    assert "/client-ws" in client_source
    assert "/v2/ws" not in app_source


def test_data_migration_is_not_part_of_production_startup():
    memory_source = (
        ROOT / "app" / "providers" / "memory" / "sqlite_memory.py"
    ).read_text("utf-8")
    migration_script = ROOT / "scripts" / "migrate_runtime_data_v3.py"

    assert "migrate_legacy_histories" not in memory_source
    assert "history_migration" not in memory_source
    assert migration_script.exists()
