from enum import Enum

from .agent import InvalidTransition


class CallState(str, Enum):
    QUEUED = "QUEUED"
    RESERVED = "RESERVED"
    INITIATED = "INITIATED"
    RINGING = "RINGING"
    ANSWERED = "ANSWERED"
    CONNECTED = "CONNECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TRANSITIONS = {
    CallState.QUEUED: {CallState.RESERVED, CallState.CANCELLED},
    CallState.RESERVED: {CallState.INITIATED, CallState.FAILED, CallState.CANCELLED},
    CallState.INITIATED: {CallState.RINGING, CallState.ANSWERED, CallState.CONNECTED, CallState.FAILED, CallState.CANCELLED},
    CallState.RINGING: {CallState.ANSWERED, CallState.CONNECTED, CallState.FAILED, CallState.CANCELLED},
    CallState.ANSWERED: {CallState.CONNECTED, CallState.COMPLETED, CallState.FAILED},
    CallState.CONNECTED: {CallState.COMPLETED, CallState.FAILED},
    CallState.COMPLETED: set(),
    CallState.FAILED: set(),
    CallState.CANCELLED: set(),
}
TERMINAL_STATES = {CallState.COMPLETED, CallState.FAILED, CallState.CANCELLED}


def transition_call(current: CallState | str, target: CallState | str) -> CallState:
    current_state, target_state = CallState(current), CallState(target)
    if current_state in TERMINAL_STATES:
        return current_state
    if target_state == current_state:
        return current_state
    if target_state in TRANSITIONS[current_state]:
        return target_state
    # Late events are ignored; forward events may safely advance over missing callbacks.
    order = [CallState.QUEUED, CallState.RESERVED, CallState.INITIATED, CallState.RINGING,
             CallState.ANSWERED, CallState.CONNECTED, CallState.COMPLETED]
    if target_state in order and current_state in order and order.index(target_state) > order.index(current_state):
        return target_state
    if target_state == CallState.FAILED and current_state not in TERMINAL_STATES:
        return target_state
    if target_state == CallState.CANCELLED and current_state in {CallState.QUEUED, CallState.RESERVED, CallState.INITIATED, CallState.RINGING}:
        return target_state
    raise InvalidTransition(f"Call cannot transition from {current_state} to {target_state}.")
