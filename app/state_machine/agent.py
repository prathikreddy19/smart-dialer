from enum import Enum


class InvalidTransition(ValueError):
    """Raised when an entity is asked to enter an illegal state."""


class AgentState(str, Enum):
    OFFLINE = "OFFLINE"
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    DIALING = "DIALING"
    CONNECTED = "CONNECTED"
    WRAP_UP = "WRAP_UP"
    PAUSED = "PAUSED"


TRANSITIONS = {
    AgentState.OFFLINE: {AgentState.AVAILABLE, AgentState.PAUSED},
    AgentState.AVAILABLE: {AgentState.RESERVED, AgentState.OFFLINE, AgentState.PAUSED},
    AgentState.RESERVED: {AgentState.DIALING, AgentState.WRAP_UP, AgentState.OFFLINE},
    AgentState.DIALING: {AgentState.CONNECTED, AgentState.WRAP_UP, AgentState.OFFLINE},
    AgentState.CONNECTED: {AgentState.WRAP_UP, AgentState.OFFLINE},
    AgentState.WRAP_UP: {AgentState.AVAILABLE, AgentState.OFFLINE, AgentState.PAUSED},
    AgentState.PAUSED: {AgentState.AVAILABLE, AgentState.OFFLINE},
}


def transition_agent(current: AgentState | str, target: AgentState | str) -> AgentState:
    current_state, target_state = AgentState(current), AgentState(target)
    if current_state == target_state:
        return target_state
    if target_state not in TRANSITIONS[current_state]:
        raise InvalidTransition(f"Agent cannot transition from {current_state} to {target_state}.")
    return target_state
