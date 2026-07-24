# Avatar Module — centralized Live2D character control
#
# Architecture:
#   Runtime → Protocol → AvatarController → Live2DProvider → Cubism SDK
#
# AvatarController is the SOLE entry point for all Live2D operations.
# No other module may call Live2DProvider directly.

from app.avatar.controller import AvatarController
from app.avatar.permission import PermissionManager, PermissionLevel, ControlEntry
from app.avatar.component_manager import ComponentManager, ComponentDef, ComponentState
from app.avatar.expression_manager import ExpressionManager, ExpressionDef, ExpressionState
from app.avatar.motion_manager import MotionManager, MotionDef, MotionState
from app.avatar.parameter_mixer import ParameterMixer, ParameterOwner, ParameterValue
from app.avatar.natural_behavior import (
    NaturalBehaviorManager,
    GazeState,
    BlinkState,
    BreathState,
    IdleMicroState,
)
from app.avatar.state import AvatarState, AvatarStateStore
from app.avatar.protocol import (
    AvatarRequest,
    AvatarSuggestion,
    AvatarComponentUpdate,
    AvatarExpressionUpdate,
    AvatarMotionUpdate,
    AvatarStateSnapshot,
    AvatarSuggestionMsg,
    AvatarRequestMsg,
    AvatarAcceptMsg,
    AvatarRejectMsg,
    AVATAR_MESSAGE_TYPES,
    serialize_avatar_message,
)

__all__ = [
    "AvatarController",
    "PermissionManager",
    "PermissionLevel",
    "ControlEntry",
    "ComponentManager",
    "ComponentDef",
    "ComponentState",
    "ExpressionManager",
    "ExpressionDef",
    "ExpressionState",
    "MotionManager",
    "MotionDef",
    "MotionState",
    "ParameterMixer",
    "ParameterOwner",
    "ParameterValue",
    "NaturalBehaviorManager",
    "GazeState",
    "BlinkState",
    "BreathState",
    "IdleMicroState",
    "AvatarState",
    "AvatarStateStore",
    "AvatarRequest",
    "AvatarSuggestion",
    "AvatarComponentUpdate",
    "AvatarExpressionUpdate",
    "AvatarMotionUpdate",
    "AvatarStateSnapshot",
    "AvatarSuggestionMsg",
    "AvatarRequestMsg",
    "AvatarAcceptMsg",
    "AvatarRejectMsg",
    "AVATAR_MESSAGE_TYPES",
    "serialize_avatar_message",
]
