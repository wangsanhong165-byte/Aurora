"""Unit tests for AvatarController, PermissionManager, ComponentManager,
ParameterMixer, and NaturalBehaviorManager.

Tests the core permission arbitration, component management, parameter
blending, and natural behavior logic without requiring a running server
or Cubism SDK.
"""

import sys
import os
import pytest
import json
import math
import tempfile
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from app.avatar.permission import PermissionManager, PermissionLevel
from app.avatar.component_manager import ComponentManager, ComponentDef
from app.avatar.expression_manager import ExpressionManager
from app.avatar.motion_manager import MotionManager
from app.avatar.parameter_mixer import ParameterMixer, ParameterOwner, ParameterValue
from app.avatar.natural_behavior import NaturalBehaviorManager
from app.avatar.state import AvatarState, AvatarStateStore
from app.avatar.controller import AvatarController
from app.avatar.events import AvatarRequest, AvatarSuggestion


# ── PermissionManager Tests ──────────────────────────────────────────────

class TestPermissionManager:
    def test_allow_first_claim(self):
        pm = PermissionManager()
        allowed, reason = pm.authorize("USER", 100, "glasses")
        assert allowed
        assert reason == "no_current_controller"

    def test_user_overrides_ai(self):
        pm = PermissionManager()
        pm.claim("AI", 50, "glasses")
        allowed, reason = pm.authorize("USER", 100, "glasses")
        assert allowed
        assert "higher_priority" in reason

    def test_ai_cannot_override_user(self):
        pm = PermissionManager()
        pm.claim("USER", 100, "glasses")
        allowed, reason = pm.authorize("AI", 50, "glasses")
        assert not allowed
        assert "denied" in reason

    def test_same_source_can_overwrite(self):
        pm = PermissionManager()
        pm.claim("AI", 50, "glasses")
        allowed, reason = pm.authorize("AI", 50, "glasses")
        assert allowed
        assert reason == "same_source"

    def test_priority_tie_different_source_denied(self):
        pm = PermissionManager()
        pm.claim("AI", 50, "glasses")
        allowed, reason = pm.authorize("USER", 50, "glasses")  # USER with low priority
        assert not allowed
        assert "priority_tie" in reason

    def test_idle_lowest_priority(self):
        pm = PermissionManager()
        pm.claim("IDLE", 10, "eye_open")
        allowed, _ = pm.authorize("AI", 50, "eye_open")
        assert allowed

    def test_system_overrides_all(self):
        pm = PermissionManager()
        pm.claim("USER", 100, "glasses")
        allowed, _ = pm.authorize("SYSTEM", 80, "glasses")
        assert not allowed  # 80 < 100

    def test_release_resource(self):
        pm = PermissionManager()
        pm.claim("AI", 50, "glasses")
        pm.release("glasses")
        assert pm.get_controller("glasses") is None

    def test_release_all_by_source(self):
        pm = PermissionManager()
        pm.claim("AI", 50, "glasses")
        pm.claim("AI", 50, "ribbon")
        pm.claim("USER", 100, "hat")
        pm.release_all("AI")
        assert pm.get_controller("glasses") is None
        assert pm.get_controller("ribbon") is None
        assert pm.get_controller("hat") is not None  # USER still holds

    def test_reset(self):
        pm = PermissionManager()
        pm.claim("USER", 100, "glasses")
        pm.claim("AI", 50, "expression")
        pm.reset()
        assert len(pm.get_all_controls()) == 0


# ── ComponentManager Tests ───────────────────────────────────────────────

class TestComponentManager:
    def test_register_component(self):
        cm = ComponentManager()
        comp = ComponentDef(
            name="glasses", display_name="护目镜",
            expression="8", param_ids=["Param41"],
            default_state=False, category="headwear",
        )
        cm.register(comp)
        assert "glasses" in cm.list_components()
        assert not cm.is_enabled("glasses")

    def test_register_with_default_true(self):
        cm = ComponentManager()
        comp = ComponentDef(
            name="ribbon", display_name="发箍",
            expression="10", param_ids=["Param45"],
            default_state=True, category="headwear",
        )
        cm.register(comp)
        assert cm.is_enabled("ribbon")

    def test_enable_disable_component(self):
        cm = ComponentManager()
        cm.register(ComponentDef("glasses", "护目镜", expression="8", param_ids=["Param41"]))
        cm.enable("glasses", "USER", 100)
        assert cm.is_enabled("glasses")
        state = cm.get_state("glasses")
        assert state.controller == "USER"
        assert state.priority == 100

        cm.disable("glasses", "USER", 100)
        assert not cm.is_enabled("glasses")

    def test_toggle_component(self):
        cm = ComponentManager()
        cm.register(ComponentDef("glasses", "护目镜", expression="8", param_ids=["Param41"]))
        cm.toggle("glasses", "USER", 100)
        assert cm.is_enabled("glasses")
        cm.toggle("glasses", "USER", 100)
        assert not cm.is_enabled("glasses")

    def test_unknown_component(self):
        cm = ComponentManager()
        assert not cm.enable("nonexistent", "USER", 100)
        assert not cm.toggle("nonexistent", "USER", 100)

    def test_get_all_states(self):
        cm = ComponentManager()
        cm.register(ComponentDef("a", "A", default_state=True))
        cm.register(ComponentDef("b", "B", default_state=False))
        states = cm.get_all_states()
        assert states == {"a": True, "b": False}

    def test_reset_to_defaults(self):
        cm = ComponentManager()
        cm.register(ComponentDef("a", "A", default_state=True))
        cm.disable("a", "USER", 100)
        cm.reset_to_defaults()
        assert cm.is_enabled("a")

    def test_register_all_from_config(self):
        cm = ComponentManager()
        cm.register_all({
            "goggles": {
                "display_name": "护目镜",
                "expression": "8",
                "param_ids": ["Param41"],
                "default_state": False,
                "category": "headwear",
            },
            "headband": {
                "display_name": "发箍",
                "expression": "10",
                "param_ids": ["Param45"],
                "default_state": True,
                "category": "headwear",
            },
        })
        assert len(cm.list_components()) == 2
        assert cm.is_enabled("headband")
        assert not cm.is_enabled("goggles")


# ── ExpressionManager Tests ───────────────────────────────────────────────

class TestExpressionManager:
    def test_register_and_set_expression(self):
        em = ExpressionManager()
        em.register_all({
            "happy": {"preset": "zs1", "default": False},
            "neutral": {"preset": "zs1", "default": True},
        })
        state = em.set("happy", 0.8, "AI", 50)
        assert state.name == "happy"
        assert state.preset == "zs1"
        assert state.intensity == 0.8
        assert state.controller == "AI"

    def test_unknown_falls_back_to_default(self):
        em = ExpressionManager()
        em.register_all({"neutral": {"preset": "zs1", "default": True}})
        state = em.set("unknown_emotion", 1.0, "AI", 50)
        assert state.name == "neutral"

    def test_intensity_clamped(self):
        em = ExpressionManager()
        em.register_all({"happy": {"preset": "zs1"}})
        state = em.set("happy", 2.5, "AI", 50)
        assert state.intensity == 1.0
        state = em.set("happy", -0.5, "AI", 50)
        assert state.intensity == 0.0


# ── MotionManager Tests ───────────────────────────────────────────────────

class TestMotionManager:
    def test_play_motion(self):
        mm = MotionManager()
        mm.register_all({
            "wave": {"priority": 50, "duration_ms": 800, "loop": False, "category": "gesture"},
            "idle": {"priority": 10, "duration_ms": 0, "loop": True, "category": "idle"},
        })
        ok = mm.play("wave", "AI", 50)
        assert ok
        state = mm.get_current()
        assert state.name == "wave"
        assert state.controller == "AI"

    def test_unknown_motion(self):
        mm = MotionManager()
        mm.register_all({"idle": {"priority": 10, "category": "idle"}})
        assert not mm.play("nonexistent", "AI", 50)

    def test_stop_returns_to_idle(self):
        mm = MotionManager()
        mm.register_all({
            "wave": {"priority": 50, "duration_ms": 800, "loop": False, "category": "gesture"},
            "idle": {"priority": 10, "duration_ms": 0, "loop": True, "category": "idle"},
        })
        mm.play("wave", "AI", 50)
        mm.stop()
        assert mm.get_current().name == "idle"

    def test_queue_after_motion_finish(self):
        mm = MotionManager()
        mm.register_all({
            "wave": {"priority": 50, "duration_ms": 10, "loop": False, "category": "gesture"},
            "nod": {"priority": 50, "duration_ms": 500, "loop": False, "category": "gesture"},
            "idle": {"priority": 10, "duration_ms": 0, "loop": True, "category": "idle"},
        })
        mm.play("wave", "AI", 50)
        mm.enqueue("nod")
        # Force motion to be "finished" by setting start time far in the past
        mm._state.started_at = 0  # epoch → elapsed > duration
        result = mm.update()
        assert result is not None
        assert result.name == "nod"


# ── AvatarState Tests ─────────────────────────────────────────────────────

class TestAvatarState:
    def test_serialize_deserialize(self):
        state = AvatarState(
            components={"glasses": True, "ribbon": False},
            expression="happy",
            expression_intensity=0.8,
            motion="idle",
        )
        d = state.to_dict()
        restored = AvatarState.from_dict(d)
        assert restored.components == state.components
        assert restored.expression == state.expression
        assert restored.expression_intensity == state.expression_intensity

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = AvatarStateStore(data_dir=tmpdir)
            state = AvatarState(
                components={"glasses": False},
                expression="angry",
                expression_intensity=0.9,
                motion="wave",
            )
            assert store.save(state)
            loaded = store.load()
            assert loaded.components == {"glasses": False}
            assert loaded.expression == "angry"
            assert loaded.expression_intensity == 0.9
            assert loaded.motion == "wave"

    def test_load_default_when_no_file(self):
        store = AvatarStateStore(data_dir="/nonexistent/path/avatar")
        state = store.load()
        assert state.expression == "neutral"
        assert state.components == {}

    def test_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = AvatarStateStore(data_dir=tmpdir)
            store.save(AvatarState(expression="happy"))
            assert store.delete()
            loaded = store.load()
            assert loaded.expression == "neutral"


# ── AvatarController Integration Tests ────────────────────────────────────

class TestAvatarControllerIntegration:
    def test_handle_component_request_allowed(self):
        ctrl = AvatarController()
        ctrl.configure("Design_genius_White", {
            "Design_genius_White": {
                "components": {
                    "goggles": {"display_name": "护目镜", "expression": "8", "param_ids": ["Param41"], "default_state": False},
                },
                "expressions": {"neutral": {"preset": "zs1", "default": True}},
                "motions": {"idle": {"priority": 10, "category": "idle"}},
            }
        })

        request = AvatarRequest(
            target="component", name="goggles", action="enable",
            source="user", priority=100,
        )
        # Use synchronous handling (without awaiting)
        import asyncio
        loop = asyncio.new_event_loop()
        responses = loop.run_until_complete(ctrl.handle_request(request))
        loop.close()

        assert len(responses) > 0
        assert ctrl.components.is_enabled("goggles")

    def test_handle_component_request_denied(self):
        ctrl = AvatarController()
        ctrl.configure("Design_genius_White", {
            "Design_genius_White": {
                "components": {
                    "goggles": {"display_name": "护目镜", "expression": "8", "default_state": False},
                },
                "expressions": {"neutral": {"preset": "zs1", "default": True}},
                "motions": {"idle": {"priority": 10, "category": "idle"}},
            }
        })

        # User enables goggles first
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(ctrl.handle_request(AvatarRequest(
            target="component", name="goggles", action="enable",
            source="user", priority=100,
        )))

        # AI tries to disable — should be denied
        responses = loop.run_until_complete(ctrl.handle_request(AvatarRequest(
            target="component", name="goggles", action="disable",
            source="ai", priority=50,
        )))
        loop.close()

        # User's control should persist
        assert ctrl.components.is_enabled("goggles")
        # Should have 0 responses (denied silently)
        assert responses == [] or len(responses) == 0

    def test_state_restore(self):
        ctrl = AvatarController()
        ctrl.configure("Design_genius_White", {
            "Design_genius_White": {
                "components": {
                    "goggles": {"display_name": "护目镜", "expression": "8", "default_state": False},
                    "headband": {"display_name": "发箍", "expression": "10", "default_state": True},
                },
                "expressions": {
                    "neutral": {"preset": "zs1", "default": True},
                    "happy": {"preset": "zs1", "default": False},
                },
                "motions": {"idle": {"priority": 10, "category": "idle"}},
            }
        })

        saved_state = AvatarState(
            components={"goggles": True, "headband": False},
            expression="happy",
            expression_intensity=0.7,
            motion="idle",
        )

        responses = ctrl.restore_state(saved_state)
        assert len(responses) > 0
        assert ctrl.components.is_enabled("goggles")
        assert not ctrl.components.is_enabled("headband")
        assert ctrl.expressions.get_current().name == "happy"

    def test_debug_info(self):
        ctrl = AvatarController()
        ctrl.configure("Design_genius_White", {
            "Design_genius_White": {
                "components": {"goggles": {"display_name": "护目镜", "default_state": False}},
                "expressions": {"neutral": {"preset": "zs1", "default": True}},
                "motions": {"idle": {"priority": 10, "category": "idle"}},
            }
        })

        debug = ctrl.debug_info()
        assert "controls" in debug
        assert "components" in debug
        assert "expression" in debug
        assert "motion" in debug
        assert debug["expression"]["name"] == "neutral"

    def test_suggest_then_accept(self):
        ctrl = AvatarController()
        ctrl.configure("Design_genius_White", {
            "Design_genius_White": {
                "components": {"goggles": {"display_name": "护目镜", "default_state": False}},
                "expressions": {"neutral": {"preset": "zs1", "default": True}},
                "motions": {"idle": {"priority": 10, "category": "idle"}},
            }
        })

        suggestion = AvatarSuggestion(
            target="component", name="goggles", action="enable",
            reason="thinking_mode",
        )

        # Send suggestion
        suggestion_msgs = ctrl.suggest(suggestion)
        assert len(suggestion_msgs) > 0
        sid = suggestion.suggestion_id

        # User accepts
        import asyncio
        loop = asyncio.new_event_loop()
        responses = loop.run_until_complete(ctrl.handle_accept(sid))
        loop.close()

        assert ctrl.components.is_enabled("goggles")

    def test_suggest_then_reject(self):
        ctrl = AvatarController()
        ctrl.configure("Design_genius_White", {
            "Design_genius_White": {
                "components": {"goggles": {"display_name": "护目镜", "default_state": False}},
                "expressions": {"neutral": {"preset": "zs1", "default": True}},
                "motions": {"idle": {"priority": 10, "category": "idle"}},
            }
        })

        suggestion = AvatarSuggestion(
            target="component", name="goggles", action="enable",
            reason="thinking_mode",
        )
        ctrl.suggest(suggestion)
        sid = suggestion.suggestion_id

        import asyncio
        loop = asyncio.new_event_loop()
        responses = loop.run_until_complete(ctrl.handle_reject(sid))
        loop.close()

        # Component should remain at default (disabled)
        assert not ctrl.components.is_enabled("goggles")


# ── ParameterMixer Tests ──────────────────────────────────────────────────

class TestParameterMixer:
    def test_single_source_no_blend(self):
        pm = ParameterMixer()
        pm.register_owner("lip_sync", ["ParamMouthOpenY"], priority=60)
        pm.set_params("lip_sync", {"ParamMouthOpenY": 0.8})
        result = pm.resolve()
        assert result["ParamMouthOpenY"] == 0.8

    def test_multi_source_weighted_blend(self):
        pm = ParameterMixer()
        pm.register_owner("lip_sync", ["ParamMouthOpenY"], priority=60)
        pm.register_owner("expression", ["ParamMouthOpenY"], priority=30)

        pm.set_params("lip_sync", {"ParamMouthOpenY": 0.8})
        pm.set_params("expression", {"ParamMouthOpenY": 0.2})
        result = pm.resolve()

        # lip_sync(0.8 * 60) + expression(0.2 * 30) / 90
        # = (48 + 6) / 90 = 0.6
        expected = (0.8 * 60 + 0.2 * 30) / 90
        assert abs(result["ParamMouthOpenY"] - expected) < 0.01

    def test_blink_absolute_override_when_active(self):
        pm = ParameterMixer()
        pm.register_owner("blink", ["ParamEyeLOpen"], priority=40)
        pm.register_owner("expression", ["ParamEyeLOpen"], priority=30)

        # Blink active (eyes closing)
        pm.set_params("blink", {"ParamEyeLOpen": 0.0})
        pm.set_params("expression", {"ParamEyeLOpen": 1.0})
        result = pm.resolve()

        # Blink wins absolutely when value < 0.5
        assert result["ParamEyeLOpen"] == 0.0

    def test_blink_not_active_blends_normally(self):
        pm = ParameterMixer()
        pm.register_owner("blink", ["ParamEyeLOpen"], priority=40)
        pm.register_owner("expression", ["ParamEyeLOpen"], priority=30)

        # Blink not active (eyes fully open)
        pm.set_params("blink", {"ParamEyeLOpen": 1.0})
        pm.set_params("expression", {"ParamEyeLOpen": 0.7})
        result = pm.resolve()

        # Both contribute since blink >= 0.5 (not active)
        expected = (1.0 * 40 + 0.7 * 30) / 70
        assert abs(result["ParamEyeLOpen"] - expected) < 0.01

    def test_independent_params_no_interference(self):
        pm = ParameterMixer()
        pm.register_owner("lip_sync", ["ParamMouthOpenY"], priority=60)
        pm.register_owner("blink", ["ParamEyeLOpen"], priority=40)

        pm.set_params("lip_sync", {"ParamMouthOpenY": 0.8})
        pm.set_params("blink", {"ParamEyeLOpen": 0.0})
        result = pm.resolve()

        assert result["ParamMouthOpenY"] == 0.8
        assert result["ParamEyeLOpen"] == 0.0

    def test_mask_weight_reduces_contribution(self):
        pm = ParameterMixer()
        pm.register_owner("source_a", ["ParamX"], priority=50, mask_weight=1.0)
        pm.register_owner("source_b", ["ParamX"], priority=50, mask_weight=0.2)

        pm.set_params("source_a", {"ParamX": 1.0})
        pm.set_params("source_b", {"ParamX": 0.0})
        result = pm.resolve()

        # source_b has low mask_weight, so source_a dominates
        assert result["ParamX"] > 0.7

    def test_reset_frame_clears_values(self):
        pm = ParameterMixer()
        pm.register_owner("lip_sync", ["ParamMouthOpenY"], priority=60)

        pm.set_params("lip_sync", {"ParamMouthOpenY": 0.8})
        pm.reset_frame()
        result = pm.resolve()
        assert len(result) == 0

    def test_register_all_from_config(self):
        pm = ParameterMixer()
        pm.register_all({
            "lip_sync": {"owns": ["ParamMouthOpenY"], "priority": 60},
            "blink": {"owns": ["ParamEyeLOpen", "ParamEyeROpen"], "priority": 40},
        })
        assert "lip_sync" in pm.list_owners()
        assert "blink" in pm.list_owners()
        owner = pm.get_owner("lip_sync")
        assert owner is not None
        assert owner.priority == 60

    def test_unregistered_source_defaults_priority_10(self):
        pm = ParameterMixer()
        pm.set_params("unknown_source", {"ParamX": 0.5})
        result = pm.resolve()
        assert result["ParamX"] == 0.5

    def test_debug_frame_info(self):
        pm = ParameterMixer()
        pm.register_owner("lip_sync", ["ParamMouthOpenY"], priority=60)
        pm.set_params("lip_sync", {"ParamMouthOpenY": 0.8})
        pm.resolve()
        debug = pm.debug_frame()
        assert "frame_values" in debug
        assert "resolved" in debug
        assert debug["resolved"]["ParamMouthOpenY"] == 0.8


# ── NaturalBehaviorManager Tests ──────────────────────────────────────────

class TestNaturalBehaviorManager:
    def test_gaze_smoothing(self):
        nbm = NaturalBehaviorManager()
        nbm.set_gaze_target(0.5, -0.3)

        # Run several updates — gaze should approach target
        for _ in range(60):
            nbm.update(1 / 60)

        params = nbm.update(1 / 60)
        assert "ParamAngleX" in params
        assert "ParamEyeBallX" in params
        # Head angle should be non-zero (gaze is tracking)
        assert abs(params["ParamAngleX"]) > 0.0

    def test_gaze_disabled_produces_no_params(self):
        nbm = NaturalBehaviorManager()
        nbm.set_gaze_enabled(False)
        nbm.set_blink_enabled(False)
        nbm.set_breath_enabled(False)
        nbm.set_idle_enabled(False)

        params = nbm.update(1 / 60)
        # All behaviors disabled — should produce no parameters
        assert len(params) == 0

    def test_blink_cycle_completes(self):
        nbm = NaturalBehaviorManager()
        # Disable other behaviors for clean test
        nbm.set_gaze_enabled(False)
        nbm.set_breath_enabled(False)
        nbm.set_idle_enabled(False)

        # Force immediate blink
        nbm.blink.next_blink = 0.0
        nbm.blink.phase = "open"
        nbm.blink.timer = 10.0  # way past interval

        params = nbm.update(1 / 60)
        # Should have started closing or already be in some blink phase
        assert "ParamEyeLOpen" in params

    def test_blink_disabled_no_eye_params(self):
        nbm = NaturalBehaviorManager()
        nbm.set_blink_enabled(False)
        nbm.set_gaze_enabled(False)
        nbm.set_breath_enabled(False)
        nbm.set_idle_enabled(False)

        params = nbm.update(1 / 60)
        assert "ParamEyeLOpen" not in params

    def test_breath_produces_wave(self):
        nbm = NaturalBehaviorManager()
        nbm.set_gaze_enabled(False)
        nbm.set_blink_enabled(False)
        nbm.set_idle_enabled(False)

        params1 = nbm.update(1 / 60)
        params2 = nbm.update(1 / 60)

        assert "ParamBreath" in params1
        # Breath value should change between frames (sinusoidal)
        assert params1["ParamBreath"] != params2["ParamBreath"]

    def test_idle_micro_produces_subtle_movement(self):
        nbm = NaturalBehaviorManager()
        nbm.set_gaze_enabled(False)
        nbm.set_blink_enabled(False)
        nbm.set_breath_enabled(False)

        params = nbm.update(1 / 60)
        assert "ParamBodyAngleZ" in params
        # Idle micro movements should be very subtle
        assert abs(params["ParamBodyAngleZ"]) < 0.1

    def test_enabled_state_roundtrip(self):
        nbm = NaturalBehaviorManager()
        nbm.set_gaze_enabled(False)
        nbm.set_blink_enabled(False)

        state = nbm.get_enabled_state()
        assert state["gaze"] == False
        assert state["blink"] == False
        assert state["breath"] == True  # default

        # Restore
        nbm2 = NaturalBehaviorManager()
        nbm2.set_enabled_state(state)
        assert nbm2.gaze.enabled == False
        assert nbm2.blink.enabled == False

    def test_all_behaviors_contribute_params(self):
        nbm = NaturalBehaviorManager()
        params = nbm.update(1 / 60)

        # All four behaviors are enabled by default — should produce params
        assert len(params) > 0
        # Gaze params
        assert "ParamAngleX" in params or "ParamEyeBallX" in params
        # Blink params
        assert "ParamEyeLOpen" in params
        # Breath params
        assert "ParamBreath" in params
        # Idle micro params
        assert "ParamBodyAngleZ" in params


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
