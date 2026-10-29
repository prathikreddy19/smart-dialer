from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Agent, AgentRuntimeState, DialerCall, ProviderEvent, SafetyDecision
from ..providers import ProviderRegistry, provider_registry
from ..state_machine import AgentState, CallState


def collect_metrics(db: Session, providers: ProviderRegistry = provider_registry) -> dict:
    total_agents = db.scalar(select(func.count(Agent.agent_id)).where(func.upper(Agent.status) == "ACTIVE")) or 0
    busy_agents = db.scalar(select(func.count(AgentRuntimeState.agent_id)).join(
        Agent, Agent.agent_id == AgentRuntimeState.agent_id,
    ).where(func.upper(Agent.status) == "ACTIVE", AgentRuntimeState.state != AgentState.AVAILABLE.value)) or 0
    calls_initiated = db.scalar(select(func.count(DialerCall.call_id))) or 0
    calls_connected = db.scalar(select(func.count(func.distinct(ProviderEvent.call_id))).where(
        ProviderEvent.event_type == CallState.CONNECTED.value,
    )) or 0
    calls_failed = db.scalar(select(func.count(DialerCall.call_id)).where(DialerCall.state == CallState.FAILED.value)) or 0
    safety_rows = db.execute(select(SafetyDecision.decision, func.count(SafetyDecision.id)).group_by(SafetyDecision.decision)).all()
    return {
        "agent_utilization": round(busy_agents / total_agents, 4) if total_agents else 0.0,
        "active_agents": total_agents,
        "busy_agents": busy_agents,
        "calls_initiated": calls_initiated,
        "calls_connected": calls_connected,
        "calls_failed": calls_failed,
        "safety_controller_decisions": {name.lower(): count for name, count in safety_rows},
        "providers": providers.metrics(),
    }
