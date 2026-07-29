"""V2 Compatibility Adapter — converts legacy V2 messages to V3 EventEnvelope.

Old clients that send V2 flat JSON messages (without protocol_version)
are routed through this adapter. Every V2 message is converted to a
V3 EventEnvelope via the compat layer, then forwarded to V3EventHandler.

No business logic lives in this layer.
"""

from __future__ import annotations

import logging
from typing import Callable

from contracts.v3.compat import v2_flat_to_v3_envelope
from contracts.v3.envelope import (
    EventEnvelope,
    error_envelope,
)

logger = logging.getLogger("transport.v2_adapter")

HandleEnvelopeFn = Callable[[EventEnvelope], list[EventEnvelope]]


class V2CompatibilityAdapter:
    """Convert V2 flat messages to V3 envelopes and route to V3 handler.

    One instance per WebSocket connection.
    """

    def __init__(self, on_envelope: HandleEnvelopeFn, default_session_id: str = ""):
        self._on_envelope = on_envelope
        self._default_session_id = default_session_id

    def handle_raw(self, raw: dict) -> list[EventEnvelope]:
        """Convert a V2 flat message dict and route to the V3 handler.

        Returns a list of response EventEnvelopes to send back.
        """
        try:
            envelope = v2_flat_to_v3_envelope(
                raw,
                default_session_id=self._default_session_id,
                source="frontend",
            )
        except Exception as exc:
            logger.warning("V2 conversion failed: %s", exc)
            return [error_envelope(
                "v2_parse_error",
                f"Failed to parse V2 message: {exc}",
            )]

        return self._on_envelope(envelope)
