from __future__ import annotations

from enum import StrEnum
from time import time
from uuid import uuid4


SCHEMA_VERSION = 1


class AvailabilityLevel(StrEnum):
    BLOCKED = "BLOCKED"
    TEXT_READY = "TEXT_READY"
    VOICE_READY = "VOICE_READY"
    FULL_READY = "FULL_READY"


class EventStream:
    def __init__(self, launch_id: str, owner_id: str):
        self.launch_id = launch_id
        self.owner_id = owner_id
        self.sequence = 0

    def event(self, event_type: str, **payload) -> dict:
        self.sequence += 1
        return {
            "schema_version": SCHEMA_VERSION,
            "launch_id": self.launch_id,
            "owner_id": self.owner_id,
            "request_id": payload.pop("request_id", None),
            "event_id": uuid4().hex,
            "sequence": self.sequence,
            "timestamp": time(),
            "type": event_type,
            "attempt": payload.pop("attempt", 1),
            "recoverable": payload.pop("recoverable", True),
            "recommended_action": payload.pop("recommended_action", None),
            **payload,
        }
