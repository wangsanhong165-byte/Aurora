from __future__ import annotations

import asyncio
import json

from fastapi import WebSocketDisconnect

from app.transport.session import WebSocketSession
from contracts.v3.events import UserTextPayload


def frame(
    event_type: str,
    payload: dict,
    *,
    sequence: int,
    event_id: str | None = None,
    turn_id: str | None = None,
    session_id: str = "session-1",
) -> dict:
    return {
        "protocolVersion": "3.0",
        "eventId": event_id or f"event-{sequence}",
        "eventType": event_type,
        "sessionId": session_id,
        "turnId": turn_id,
        "sequence": sequence,
        "source": "frontend",
        "timestamp": 1.0 + sequence,
        "payload": payload,
    }


class WebSocketProbe:
    def __init__(self, incoming: list[dict]):
        self.incoming = [json.dumps(item) for item in incoming]
        self.sent: list[dict] = []

    async def accept(self) -> None:
        pass

    async def receive_text(self) -> str:
        if not self.incoming:
            raise WebSocketDisconnect()
        return self.incoming.pop(0)

    async def send_text(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


def run_session(incoming: list[dict], received: list | None = None) -> WebSocketProbe:
    probe = WebSocketProbe(incoming)

    async def handler(event):
        if received is not None:
            received.append(event)
        return []

    asyncio.run(WebSocketSession(probe, handler, ping_interval=3600).run())
    return probe


def test_session_binds_to_client_session_open_before_dispatch() -> None:
    received: list = []
    probe = run_session([
        frame("session.open", {"capabilities": ["text"]}, sequence=1),
        frame("user.text", {"text": "hello"}, sequence=2, turn_id="turn-1"),
    ], received)

    assert probe.sent[0]["eventType"] == "session.opened"
    assert probe.sent[0]["sessionId"] == "session-1"
    assert len(received) == 1
    assert received[0].event_type == "user.text"
    assert isinstance(received[0].payload, UserTextPayload)


def test_v2_flat_frame_is_rejected_without_dispatch() -> None:
    received: list = []
    probe = run_session([{"type": "text_input", "text": "hello"}], received)

    assert received == []
    assert probe.sent[-1]["eventType"] == "protocol.error"
    assert probe.sent[-1]["payload"]["code"] == "v3_required"


def test_duplicate_event_id_is_idempotent() -> None:
    received: list = []
    probe = run_session([
        frame("session.open", {"capabilities": []}, sequence=1),
        frame("user.text", {"text": "hello"}, sequence=2, event_id="same", turn_id="turn-1"),
        frame("user.text", {"text": "hello"}, sequence=3, event_id="same", turn_id="turn-1"),
    ], received)

    assert len(received) == 1
    assert not any(message["payload"].get("code") == "duplicate_event" for message in probe.sent)


def test_sequence_gap_is_rejected_before_handler() -> None:
    received: list = []
    probe = run_session([
        frame("session.open", {"capabilities": []}, sequence=1),
        frame("user.text", {"text": "hello"}, sequence=3, turn_id="turn-1"),
    ], received)

    assert received == []
    assert probe.sent[-1]["payload"]["code"] == "sequence_gap"


def test_out_of_order_sequence_is_rejected() -> None:
    received: list = []
    probe = run_session([
        frame("session.open", {"capabilities": []}, sequence=1),
        frame("session.ping", {"nonce": "one"}, sequence=2),
        frame("session.ping", {"nonce": "old"}, sequence=2, event_id="event-old"),
    ], received)

    assert probe.sent[-1]["payload"]["code"] == "out_of_order"


def test_unknown_event_and_bad_payload_return_protocol_error() -> None:
    unknown = run_session([
        frame("session.open", {"capabilities": []}, sequence=1),
        frame("unknown.event", {}, sequence=2),
    ])
    invalid = run_session([
        frame("session.open", {"capabilities": []}, sequence=1),
        frame("user.text", {"text": 42}, sequence=2, turn_id="turn-1"),
    ])

    assert unknown.sent[-1]["payload"]["code"] == "unsupported_event"
    assert invalid.sent[-1]["payload"]["code"] == "invalid_payload"


def test_session_id_change_is_rejected() -> None:
    received: list = []
    probe = run_session([
        frame("session.open", {"capabilities": []}, sequence=1),
        frame(
            "user.text",
            {"text": "hello"},
            sequence=2,
            turn_id="turn-1",
            session_id="session-other",
        ),
    ], received)

    assert received == []
    assert probe.sent[-1]["payload"]["code"] == "session_mismatch"
