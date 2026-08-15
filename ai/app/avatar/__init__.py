# Avatar Module — explicit Live2D protocol and state control
#
# Architecture:
#   Explicit UI/AI requests → Protocol → AvatarController → frontend controllers

from app.avatar.controller import AvatarController
from app.avatar.permission import PermissionManager, PermissionLevel, ControlEntry
from app.avatar.component_manager import ComponentManager, ComponentDef, ComponentState
from app.avatar.expression_manager import ExpressionManager, ExpressionDef, ExpressionState
from app.avatar.motion_manager import MotionManager, MotionDef, MotionState
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
    "AvatarState",
    "AvatarStateStore",
    "AvatarRequest",
    "AvatarSuggestion",
    "AvatarEvent",
    "AvatarComponentChanged",
    "AvatarExpressionChanged",
    "AvatarMotionChanged",
    "AvatarStateRestored",
    "AvatarSuggestionCreated",
]
