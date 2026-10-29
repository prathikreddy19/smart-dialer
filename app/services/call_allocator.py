from datetime import timedelta
import logging
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import Agent, AgentRuntimeState, Borrower, Campaign, DialerCall, ProviderEvent, SafetyDecision
from ..providers import ProviderEventData, ProviderRegistry, provider_registry
from ..state_machine import AgentState, CallState, InvalidTransition, transition_agent, transition_call
from ..utils import utcnow_naive
from .pacing import PacingInput, PredictivePacingEngine
from .safety import SafetyController

logger = logging.getLogger(__name__)
ACTIVE_CALLS = {CallState.QUEUED.value, CallState.RESERVED.value, CallState.INITIATED.value,
                CallState.RINGING.value, CallState.ANSWERED.value, CallState.CONNECTED.value}


class CallAllocator:
    def __init__(self, providers: ProviderRegistry = provider_registry) -> None:
        self.providers = providers
        self.pacing = PredictivePacingEngine()
        self.safety = SafetyController()

    def start_campaign(
        self, db: Session, campaign_id: str, mode: str = "progressive", provider_name: str = "provider_a",
        max_calls: int = 100, answer_rate: float = 0.5, average_call_duration_seconds: float = 120,
    ) -> dict:
        campaign = db.get(Campaign, campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign '{campaign_id}' was not found.")
        if mode not in {"progressive", "predictive"}:
            raise ValueError("mode must be 'progressive' or 'predictive'.")
        if max_calls < 1 or not 0 <= answer_rate <= 1:
            raise ValueError("max_calls must be positive and answer_rate must be between 0 and 1.")
        provider = self.providers.get(provider_name)
        now = utcnow_naive()

        try:
            available_count = self._count_available_agents(db)
            if mode == "predictive":
                recommendation = self.pacing.recommend(PacingInput(
                    available_agents=available_count,
                    answer_rate=answer_rate,
                    average_call_duration_seconds=average_call_duration_seconds,
                    provider_health=provider.health,
                ))
                recommended = min(recommendation.recommended_calls, max_calls)
                pacing_reason = recommendation.explanation
            else:
                recommended = min(available_count, max_calls)
                pacing_reason = "Progressive mode recommends at most one call per available agent."

            agents = self._lock_available_agents(db, recommended)
            borrowers = self._lock_eligible_borrowers(db, campaign_id, recommended)
            safety = self.safety.evaluate(
                recommended, len(agents), len(borrowers), provider.health,
                predictive=mode == "predictive",
            )
            approved = min(safety.approved_calls, max_calls)
            selected_agents, selected_borrowers = agents[:approved], borrowers[:approved]
            calls: list[DialerCall] = []
            for agent, borrower in zip(selected_agents, selected_borrowers):
                runtime = db.get(AgentRuntimeState, agent.agent_id)
                if runtime is None:
                    runtime = AgentRuntimeState(agent_id=agent.agent_id, state=AgentState.AVAILABLE.value, updated_at=now)
                    db.add(runtime)
                runtime.state = transition_agent(runtime.state, AgentState.RESERVED).value
                runtime.updated_at = now
                call = DialerCall(
                    call_id=str(uuid4()), campaign_id=campaign_id, borrower_id=borrower.borrower_id,
                    agent_id=agent.agent_id, provider=provider.name, state=CallState.QUEUED.value,
                    created_at=now, updated_at=now,
                )
                call.state = transition_call(call.state, CallState.RESERVED).value
                call.state = transition_call(call.state, CallState.INITIATED).value
                runtime.state = transition_agent(runtime.state, AgentState.DIALING).value
                db.add(call)
                calls.append(call)

            if approved < recommended and safety.decision == "APPROVED":
                decision, reason = "REDUCED", "Concurrent reservations or available borrowers limited the safe count."
            else:
                decision, reason = safety.decision, f"{pacing_reason} {safety.reason}"
            db.add(SafetyDecision(
                campaign_id=campaign_id, mode=mode, recommended=recommended, approved=len(calls),
                decision=decision, reason=reason[:255], created_at=now,
            ))
            db.commit()
        except (SQLAlchemyError, InvalidTransition):
            db.rollback()
            raise

        # Provider calls are made after reservation commits; locks are never held across network I/O.
        for call in calls:
            try:
                events = provider.place_call(call.call_id, answer_rate)
            except TimeoutError:
                logger.warning("Provider timeout for call %s", call.call_id)
                events = [ProviderEventData(event_id=f"timeout-{call.call_id}", event_type="FAILED")]
            except Exception:
                logger.exception("Provider request failed for call %s", call.call_id)
                events = [ProviderEventData(event_id=f"provider-error-{call.call_id}", event_type="FAILED")]
            for event in events:
                self.apply_provider_event(db, call.call_id, provider.name, event)

        return {
            "campaign_id": campaign_id,
            "mode": mode,
            "provider": provider.name,
            "recommended_calls": recommended,
            "initiated_calls": len(calls),
            "safety_decision": decision,
            "safety_reason": reason,
            "calls": [self.call_to_dict(db.get(DialerCall, call.call_id)) for call in calls],
        }

    @staticmethod
    def _count_available_agents(db: Session) -> int:
        return db.scalar(
            select(func.count(Agent.agent_id)).outerjoin(
                AgentRuntimeState, AgentRuntimeState.agent_id == Agent.agent_id,
            ).where(
                func.upper(Agent.status) == "ACTIVE",
                or_(AgentRuntimeState.agent_id.is_(None), AgentRuntimeState.state == AgentState.AVAILABLE.value),
            )
        ) or 0

    @staticmethod
    def _lock_available_agents(db: Session, limit: int) -> list[Agent]:
        if limit <= 0:
            return []
        statement = select(Agent).outerjoin(
            AgentRuntimeState, AgentRuntimeState.agent_id == Agent.agent_id,
        ).where(
            func.upper(Agent.status) == "ACTIVE",
            or_(AgentRuntimeState.agent_id.is_(None), AgentRuntimeState.state == AgentState.AVAILABLE.value),
        ).order_by(Agent.agent_id).limit(limit).with_for_update(skip_locked=True)
        return list(db.scalars(statement).all())

    @staticmethod
    def _lock_eligible_borrowers(db: Session, campaign_id: str, limit: int) -> list[Borrower]:
        used = select(DialerCall.call_id).where(
            DialerCall.campaign_id == campaign_id,
            DialerCall.borrower_id == Borrower.borrower_id,
        ).exists()
        statement = select(Borrower).where(~used).order_by(Borrower.borrower_id).limit(limit).with_for_update(skip_locked=True)
        return list(db.scalars(statement).all())

    def apply_provider_event(self, db: Session, call_id: str, provider: str, event: ProviderEventData) -> bool:
        call = db.scalar(select(DialerCall).where(DialerCall.call_id == call_id).with_for_update())
        if call is None:
            raise ValueError(f"Call '{call_id}' was not found.")
        duplicate = db.scalar(select(ProviderEvent.id).where(
            ProviderEvent.provider == provider, ProviderEvent.event_id == event.event_id,
        ))
        if duplicate is not None:
            return False
        try:
            event_type = event.event_type.upper()
            target = CallState(event_type)
            call.state = transition_call(call.state, target).value
            call.updated_at = utcnow_naive()
            runtime = db.get(AgentRuntimeState, call.agent_id)
            if runtime is not None:
                if target == CallState.CONNECTED and call.state == CallState.CONNECTED.value:
                    runtime.state = transition_agent(runtime.state, AgentState.CONNECTED).value
                elif call.state in {CallState.COMPLETED.value, CallState.FAILED.value, CallState.CANCELLED.value}:
                    if runtime.state not in {AgentState.WRAP_UP.value, AgentState.AVAILABLE.value, AgentState.OFFLINE.value}:
                        runtime.state = transition_agent(runtime.state, AgentState.WRAP_UP).value
                    if runtime.state == AgentState.WRAP_UP.value:
                        runtime.state = transition_agent(runtime.state, AgentState.AVAILABLE).value
                runtime.updated_at = call.updated_at
            db.add(ProviderEvent(
                call_id=call_id, provider=provider, event_id=event.event_id,
                event_type=event_type, received_at=call.updated_at,
            ))
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False
        except (ValueError, SQLAlchemyError):
            db.rollback()
            raise

    @staticmethod
    def call_to_dict(call: DialerCall) -> dict:
        return {
            "call_id": call.call_id, "campaign_id": call.campaign_id, "borrower_id": call.borrower_id,
            "agent_id": call.agent_id, "provider": call.provider, "state": call.state,
            "created_at": call.created_at.isoformat(), "updated_at": call.updated_at.isoformat(),
        }


def set_agent_state(db: Session, agent_id: str, target_state: AgentState) -> AgentRuntimeState:
    agent = db.scalar(select(Agent).where(Agent.agent_id == agent_id).with_for_update())
    if agent is None:
        raise ValueError(f"Agent '{agent_id}' was not found.")
    if target_state == AgentState.AVAILABLE and agent.status.upper() != "ACTIVE":
        raise ValueError("Only active agents can be made available.")
    runtime = db.get(AgentRuntimeState, agent_id)
    now = utcnow_naive()
    if runtime is None:
        initial = AgentState.AVAILABLE if agent.status.upper() == "ACTIVE" else AgentState.OFFLINE
        runtime = AgentRuntimeState(agent_id=agent_id, state=initial.value, updated_at=now)
        db.add(runtime)
        db.flush()
    runtime.state = transition_agent(runtime.state, target_state).value
    runtime.updated_at = now
    if target_state in {AgentState.OFFLINE, AgentState.PAUSED}:
        calls = db.scalars(select(DialerCall).where(
            DialerCall.agent_id == agent_id, DialerCall.state.in_(ACTIVE_CALLS),
        ).with_for_update()).all()
        for call in calls:
            call.state = transition_call(call.state, CallState.CANCELLED).value
            call.updated_at = now
    return runtime


def recover_stale_calls(db: Session, timeout_seconds: int = 60) -> int:
    cutoff = utcnow_naive() - timedelta(seconds=timeout_seconds)
    stale = db.scalars(select(DialerCall).where(
        DialerCall.state.in_([CallState.QUEUED.value, CallState.RESERVED.value, CallState.INITIATED.value, CallState.RINGING.value]),
        DialerCall.updated_at < cutoff,
    ).with_for_update(skip_locked=True)).all()
    now = utcnow_naive()
    for call in stale:
        call.state = CallState.CANCELLED.value
        call.updated_at = now
        runtime = db.get(AgentRuntimeState, call.agent_id)
        if runtime and runtime.state in {AgentState.RESERVED.value, AgentState.DIALING.value}:
            runtime.state = AgentState.WRAP_UP.value
            runtime.state = AgentState.AVAILABLE.value
            runtime.updated_at = now
    db.commit()
    return len(stale)
