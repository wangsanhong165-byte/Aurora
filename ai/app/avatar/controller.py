# Avatar Controller — sole entry point for all Live2D character control
# Enforces: Runtime → Protocol → AvatarController → Live2DProvider
# No other module may call Live2DProvider directly.

from dataclasses import dataclass, field
import logging
import uuid
from typing import Any

from app.avatar.permission import PermissionManager, PermissionLevel
from app.avatar.component_manager import ComponentManager
from app.avatar.expression_manager import ExpressionManager
from app.avatar.motion_manager import MotionManager
from app.avatar.parameter_mixer import ParameterMixer
from app.avatar.natural_behavior import NaturalBehaviorManager
from app.avatar.state import AvatarState, AvatarStateStore
from app.avatar.protocol import (
    AvatarRequest,
    AvatarSuggestion,
    AvatarComponentUpdate,
    AvatarExpressionUpdate,
    AvatarMotionUpdate,
    AvatarStateSnapshot,
    AvatarSuggestionMsg,
    serialize_avatar_message,
)

logger = logging.getLogger("avatar.controller")


class AvatarController:
    """Central avatar control authority.

    All Live2D operations — expression, motion, component visibility,
    parameter blending — MUST go through this controller. Direct calls
    to Live2DProvider from any other module are forbidden.

    Supports dual-control (Human + AI) with priority-based arbitration:
    USER(100) > SYSTEM(80) > AI(50) > IDLE(10)
    """

    def __init__(self, data_dir: str | None = None):
        self.permission = PermissionManager()
        self.components = ComponentManager()
        self.expressions = ExpressionManager()
        self.motions = MotionManager()
        self.mixer = ParameterMixer()
        self.behavior = NaturalBehaviorManager()
        self.state_store = AvatarStateStore(data_dir)

        # Pending AI suggestions (keyed by suggestion_id)
        self._pending_suggestions: dict[str, AvatarSuggestion] = {}

        # Callback for pushing messages to frontend via transport layer
        self._on_push: Any = None

    # ── Configuration ──────────────────────────────────────────────────

    def configure(self, model_id: str, avatar_config: dict) -> None:
        """Load per-model configuration from avatar.yaml."""
        model_cfg = avatar_config.get(model_id, {})

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

        parameters = model_cfg.get("parameters", {})
        self.mixer.register_all(parameters)
        logger.info("AvatarController configured: parameter_owners=%d", len(parameters))

    def set_push_callback(self, callback: Any) -> None:
        """Set callback for pushing messages to frontend via WebSocket."""
        self._on_push = callback

    # ── Request Handling ───────────────────────────────────────────────

    async def handle_request(self, request: AvatarRequest) -> list[dict]:
        """Process an avatar control request with permission arbitration.

        Returns list of outgoing messages to send to frontend.
        """
        responses: list[dict] = []

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

    def _handle_component_request(self, req: AvatarRequest) -> list[dict]:
        responses: list[dict] = []
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
            responses.append(serialize_avatar_message(AvatarComponentUpdate(
                name=req.name,
                display_name=comp.display_name if comp else req.name,
                enabled=state.enabled,
                controller=state.controller,
                priority=state.priority,
                expression=comp.expression if comp else "",
                param_ids=comp.param_ids if comp else [],
            )))

        return responses

    def _handle_expression_request(self, req: AvatarRequest) -> list[dict]:
        responses: list[dict] = []
        intensity = 1.0
        state = self.expressions.set(req.name, intensity, req.source, req.priority)
        self.permission.claim(req.source, req.priority, req.name)
        responses.append(serialize_avatar_message(AvatarExpressionUpdate(
            name=state.name,
            intensity=state.intensity,
            controller=state.controller,
            priority=state.priority,
        )))
        return responses

    def _handle_motion_request(self, req: AvatarRequest) -> list[dict]:
        responses: list[dict] = []
        ok = self.motions.play(req.name, req.source, req.priority)
        if ok:
            self.permission.claim(req.source, req.priority, req.name)
            state = self.motions.get_current()
            responses.append(serialize_avatar_message(AvatarMotionUpdate(
                name=state.name,
                controller=state.controller,
                priority=state.priority,
                loop=state.loop,
            )))
        return responses

    # ── AI Suggestion ──────────────────────────────────────────────────

    def suggest(self, suggestion: AvatarSuggestion) -> list[dict]:
        """Send an AI suggestion to the frontend for user approval."""
        sid = suggestion.suggestion_id or str(uuid.uuid4())[:8]
        suggestion.suggestion_id = sid
        self._pending_suggestions[sid] = suggestion
        msg = AvatarSuggestionMsg(
            target=suggestion.target,
            name=suggestion.name,
            action=suggestion.action,
            reason=suggestion.reason,
            suggestion_id=sid,
        )
        logger.info("AI suggestion: %s.%s → %s (reason: %s, id=%s)",
                     suggestion.target, suggestion.name, suggestion.action,
                     suggestion.reason, sid)
        return [serialize_avatar_message(msg)]

    async def handle_accept(self, suggestion_id: str) -> list[dict]:
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

    async def handle_reject(self, suggestion_id: str) -> list[dict]:
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

    def restore_state(self, state: AvatarState | None = None) -> list[dict]:
        """Restore avatar state from disk or provided state. Returns init messages."""
        if state is None:
            state = self.state_store.load()

        responses: list[dict] = []

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
        responses.append(serialize_avatar_message(AvatarStateSnapshot(
            components=self.components.get_all_states(),
            expression=state.expression,
            expression_intensity=state.expression_intensity,
            motion=state.motion,
            model_id=state.model_id,
        )))

        # Also send component payload
        payload = self.components.to_frontend_payload()
        for name, enabled in payload["state"].items():
            responses.append(serialize_avatar_message(AvatarComponentUpdate(
                name=name,
                display_name=name,
                enabled=enabled,
                controller="SYSTEM",
                priority=80,
                expression=payload["parts"].get(name, ""),
            )))

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

    # ── Per-Frame Parameter Update ──────────────────────────────────────

    def update_frame(self, dt: float, lip_sync_params: dict[str, float] | None = None,
                     expression_params: dict[str, float] | None = None) -> dict[str, float]:
        """Advance one frame: natural behaviors + optional lip-sync/expression.

        Call this each frame before rendering. The flow:
        1. Submit lip-sync params (TTS-driven mouth) at priority 60
        2. Submit expression params (emotion-driven brow/mouth) at priority 30
        3. Advance NaturalBehaviorManager → submits gaze/blink/breath at priority 10
        4. resolve() blends all sources into final parameter values

        Returns {param_id: final_value} for the Cubism model.
        """
        self.mixer.reset_frame()

        # Layer 1: Natural behaviors (IDLE priority, always runs)
        natural_params = self.behavior.update(dt)
        self.mixer.set_params("natural", natural_params, self.behavior.PRIORITY)

        # Layer 2: Expression (AI emotion decision)
        if expression_params:
            self.mixer.set_params("expression", expression_params, priority=30)

        # Layer 3: Lip sync (TTS audio analysis)
        if lip_sync_params:
            self.mixer.set_params("lip_sync", lip_sync_params, priority=60)

        return self.mixer.resolve()

    def set_gaze_target(self, x: float, y: float) -> None:
        """Update mouse gaze target (normalized -1..1)."""
        self.behavior.set_gaze_target(x, y)

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
            "mixer": self.mixer.debug_frame(),
            "behavior": self.behavior.get_enabled_state(),
            "pending_suggestions": len(self._pending_suggestions),
        }

    def reset(self) -> None:
        """Full reset — clear all state."""
        self.permission.reset()
        self.components.reset_to_defaults()
        self.expressions.reset()
        self.motions.stop()
        self.mixer.reset_frame()
        self.behavior = NaturalBehaviorManager()
        self._pending_suggestions.clear()
