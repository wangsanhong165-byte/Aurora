# Avatar Controller — explicit avatar protocol and persisted-state authority.

from dataclasses import dataclass, field
import logging
import uuid
from typing import Any

from app.avatar.permission import PermissionManager, PermissionLevel
from app.avatar.component_manager import ComponentManager
from app.avatar.expression_manager import ExpressionManager
from app.avatar.motion_manager import MotionManager
from app.avatar.state import AvatarState, AvatarStateStore
from app.avatar.events import (
    AvatarEvent,
    AvatarRequest,
    AvatarSuggestion,
    AvatarComponentChanged,
    AvatarExpressionChanged,
    AvatarMotionChanged,
    AvatarStateRestored,
    AvatarSuggestionCreated,
)

logger = logging.getLogger("avatar.controller")


class AvatarController:
    """Explicit component/expression/motion protocol authority.

    The normal LLM presentation path is ``character.intent`` and is resolved
    by the frontend PerformanceDirector.  This controller owns explicit user
    controls, suggestions, and persisted avatar state; it does not run a
    second per-frame Live2D parameter system.

    Supports dual-control (Human + AI) with priority-based arbitration:
    USER(100) > SYSTEM(80) > AI(50) > IDLE(10)
    """

    def __init__(self, data_dir: str | None = None):
        self.permission = PermissionManager()
        self.components = ComponentManager()
        self.expressions = ExpressionManager()
        self.motions = MotionManager()
        self.state_store = AvatarStateStore(data_dir)

        # Pending AI suggestions (keyed by suggestion_id)
        self._pending_suggestions: dict[str, AvatarSuggestion] = {}

        # Callback for pushing messages to frontend via transport layer
        self._on_push: Any = None

    # ── Configuration ──────────────────────────────────────────────────

    def configure(self, model_id: str, avatar_config: dict) -> None:
        """Replace the explicit-control catalog with one model's config."""
        model_cfg = avatar_config.get(model_id, {})

        # A model switch replaces, rather than extends, the previous catalog.
        # Keeping old definitions made explicit controls from the last model
        # appear valid after a switch.
        self.permission.reset()
        self.components = ComponentManager()
        self.expressions = ExpressionManager()
        self.motions = MotionManager()
        self._pending_suggestions.clear()

        components = model_cfg.get("components", {})
        self.components.register_all(components)
        logger.info("AvatarController configured: model=%s, components=%d",
                     model_id, len(components))

        expressions = model_cfg.get("expressions", {})
        self.expressions.register_all(expressions)
        logger.info("AvatarController configured: expressions=%d", len(expressions))

        motions = model_cfg.get("motions", {})
        self.motions.register_all(motions)
        logger.info("AvatarController configured: motions=%d", len(motions))

    def set_push_callback(self, callback: Any) -> None:
        """Set callback for pushing messages to frontend via WebSocket."""
        self._on_push = callback

    # ── Request Handling ───────────────────────────────────────────────

    async def handle_request(self, request: AvatarRequest) -> list[AvatarEvent]:
        """Process an avatar control request with permission arbitration.

        Returns list of outgoing messages to send to frontend.
        """
        responses: list[AvatarEvent] = []

        allowed, reason = self.permission.authorize(
            request.source, request.priority, request.name,
        )

        if not allowed:
            logger.info("Avatar request DENIED: %s.%s (%s) — %s",
                         request.target, request.name, request.source, reason)
            return responses

        logger.info("Avatar request: %s.%s → %s (by %s, priority=%d)",
                     request.target, request.name, request.action, request.source, request.priority)

        if request.target == "component":
            responses.extend(self._handle_component_request(request))
        elif request.target == "expression":
            responses.extend(self._handle_expression_request(request))
        elif request.target == "motion":
            responses.extend(self._handle_motion_request(request))
        else:
            logger.warning("Unknown request target: %s", request.target)

        # Persist state after any change
        self._save_state()

        return responses

    def _handle_component_request(self, req: AvatarRequest) -> list[AvatarEvent]:
        responses: list[AvatarEvent] = []
        comp = self.components.get_def(req.name)

        if req.action == "toggle":
            self.components.toggle(req.name, req.source, req.priority)
        elif req.action == "enable":
            self.components.enable(req.name, req.source, req.priority)
        elif req.action == "disable":
            self.components.disable(req.name, req.source, req.priority)
        else:
            logger.warning("Unknown component action: %s", req.action)
            return responses

        self.permission.claim(req.source, req.priority, req.name)
        state = self.components.get_state(req.name)
        if state:
            responses.append(AvatarComponentChanged(
                name=req.name,
                display_name=comp.display_name if comp else req.name,
                enabled=state.enabled,
                controller=state.controller,
                priority=state.priority,
                expression=comp.expression if comp else "",
                param_ids=comp.param_ids if comp else [],
            ))

        return responses

    def _handle_expression_request(self, req: AvatarRequest) -> list[AvatarEvent]:
        responses: list[AvatarEvent] = []
        intensity = 1.0
        state = self.expressions.set(req.name, intensity, req.source, req.priority)
        self.permission.claim(req.source, req.priority, req.name)
        responses.append(AvatarExpressionChanged(
            name=state.name,
            intensity=state.intensity,
            controller=state.controller,
            priority=state.priority,
        ))
        return responses

    def _handle_motion_request(self, req: AvatarRequest) -> list[AvatarEvent]:
        responses: list[AvatarEvent] = []
        ok = self.motions.play(req.name, req.source, req.priority)
        if ok:
            self.permission.claim(req.source, req.priority, req.name)
            state = self.motions.get_current()
            responses.append(AvatarMotionChanged(
                name=state.name,
                controller=state.controller,
                priority=state.priority,
                loop=state.loop,
            ))
        return responses

    # ── AI Suggestion ──────────────────────────────────────────────────

    def suggest(self, suggestion: AvatarSuggestion) -> list[AvatarEvent]:
        """Send an AI suggestion to the frontend for user approval."""
        sid = suggestion.suggestion_id or str(uuid.uuid4())[:8]
        suggestion.suggestion_id = sid
        self._pending_suggestions[sid] = suggestion
        event = AvatarSuggestionCreated(
            target=suggestion.target,
            name=suggestion.name,
            action=suggestion.action,
            reason=suggestion.reason,
            suggestion_id=sid,
        )
        logger.info("AI suggestion: %s.%s → %s (reason: %s, id=%s)",
                     suggestion.target, suggestion.name, suggestion.action,
                     suggestion.reason, sid)
        return [event]

    async def handle_accept(self, suggestion_id: str) -> list[AvatarEvent]:
        """User accepted an AI suggestion. Convert to request and execute."""
        suggestion = self._pending_suggestions.pop(suggestion_id, None)
        if suggestion is None:
            logger.warning("Accept for unknown suggestion: %s", suggestion_id)
            return []
        request = AvatarRequest(
            target=suggestion.target,
            name=suggestion.name,
            action=suggestion.action,
            source="user",
            priority=PermissionLevel.USER,
            reason=suggestion.reason,
        )
        return await self.handle_request(request)

    async def handle_reject(self, suggestion_id: str) -> list[AvatarEvent]:
        """User rejected an AI suggestion. Just remove it."""
        suggestion = self._pending_suggestions.pop(suggestion_id, None)
        if suggestion:
            logger.info("AI suggestion rejected: %s (%s)", suggestion_id, suggestion.reason)
        return []

    # ── State Persistence ───────────────────────────────────────────────

    def get_state_snapshot(self) -> AvatarState:
        """Build an AvatarState from current runtime state."""
        expr = self.expressions.get_current()
        motion = self.motions.get_current()
        return AvatarState(
            components=self.components.get_all_states(),
            expression=expr.name,
            expression_intensity=expr.intensity,
            motion=motion.name,
            timestamp=0.0,
        )

    def _save_state(self) -> None:
        self.state_store.save(self.get_state_snapshot())

    def restore_state(self, state: AvatarState | None = None) -> list[AvatarEvent]:
        """Restore avatar state from disk or provided state. Returns init messages."""
        if state is None:
            state = self.state_store.load()

        responses: list[AvatarEvent] = []

        # Restore components
        for name, enabled in state.components.items():
            if enabled:
                self.components.enable(name, "SYSTEM", PermissionLevel.SYSTEM)
            else:
                self.components.disable(name, "SYSTEM", PermissionLevel.SYSTEM)
            self.permission.claim("SYSTEM", PermissionLevel.SYSTEM, name)

        # Restore expression
        self.expressions.set(state.expression, state.expression_intensity,
                             "SYSTEM", PermissionLevel.SYSTEM)

        # Restore motion
        self.motions.play(state.motion, "SYSTEM", PermissionLevel.SYSTEM)

        # Build state snapshot for frontend
        responses.append(AvatarStateRestored(
            components=self.components.get_all_states(),
            expression=state.expression,
            expression_intensity=state.expression_intensity,
            motion=state.motion,
        ))

        # Also send component payload
        payload = self.components.to_frontend_payload()
        for name, enabled in payload["state"].items():
            responses.append(AvatarComponentChanged(
                name=name,
                display_name=name,
                enabled=enabled,
                controller="SYSTEM",
                priority=80,
                expression=payload["parts"].get(name, ""),
            ))

        return responses

    def get_full_state_for_frontend(self) -> dict:
        """Build a complete state payload for frontend initialization."""
        expr = self.expressions.get_current()
        motion = self.motions.get_current()
        return {
            "components": self.components.get_all_states(),
            "expression": expr.name,
            "expression_preset": expr.preset,
            "expression_intensity": expr.intensity,
            "motion": motion.name,
            "motion_loop": motion.loop,
        }

    # ── Debug ───────────────────────────────────────────────────────────

    def debug_info(self) -> dict:
        """Return debug information about current avatar state and controllers."""
        return {
            "controls": {
                resource: {
                    "controller": entry.controller,
                    "priority": entry.priority,
                }
                for resource, entry in self.permission.get_all_controls().items()
            },
            "components": self.components.get_all_states(),
            "expression": {
                "name": self.expressions.get_current().name,
                "preset": self.expressions.get_current().preset,
                "intensity": self.expressions.get_current().intensity,
                "controller": self.expressions.get_current().controller,
            },
            "motion": {
                "name": self.motions.get_current().name,
                "controller": self.motions.get_current().controller,
                "priority": self.motions.get_current().priority,
            },
            "pending_suggestions": len(self._pending_suggestions),
        }

    def reset(self) -> None:
        """Full reset — clear all state."""
        self.permission.reset()
        self.components.reset_to_defaults()
        self.expressions.reset()
        self.motions.stop()
        self._pending_suggestions.clear()
