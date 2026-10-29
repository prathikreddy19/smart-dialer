import pytest

from app.state_machine import AgentState, CallState, InvalidTransition, transition_agent, transition_call


def test_agent_transition_rules_and_idempotency():
    assert transition_agent(AgentState.AVAILABLE, AgentState.RESERVED) == AgentState.RESERVED
    assert transition_agent(AgentState.AVAILABLE, AgentState.AVAILABLE) == AgentState.AVAILABLE
    with pytest.raises(InvalidTransition):
        transition_agent(AgentState.CONNECTED, AgentState.RESERVED)


def test_call_duplicate_and_out_of_order_events_are_safe():
    state = transition_call(CallState.INITIATED, CallState.COMPLETED)
    assert state == CallState.COMPLETED
    assert transition_call(state, CallState.ANSWERED) == CallState.COMPLETED
    assert transition_call(state, CallState.COMPLETED) == CallState.COMPLETED


def test_call_rejects_invalid_reverse_transition():
    with pytest.raises(InvalidTransition):
        transition_call(CallState.RINGING, CallState.RESERVED)
