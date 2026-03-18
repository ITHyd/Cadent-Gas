"""Session mode enum for agent orchestrator state management."""
from enum import Enum


class SessionMode(str, Enum):
    IDLE = "idle"
    IN_WORKFLOW = "in_workflow"
    CONFIRM_SWITCH = "confirm_switch"
    SMALL_TALK = "small_talk"
