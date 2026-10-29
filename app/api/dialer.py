from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..models import Agent, AgentRuntimeState, Borrower, Call, Campaign, DialerCall
from ..schemas import AgentStateUpdate, DialRequest, ProviderEventRequest, SimulationRequest
from ..services.call_allocator import CallAllocator, recover_stale_calls, set_agent_state
from ..services.metrics import collect_metrics
from ..simulator import SimulationEngine
from ..state_machine import AgentState

router = APIRouter(tags=["Smart Dialer"])
allocator = CallAllocator()


@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db)):
    return [{"campaign_id": row.campaign_id, "campaign_name": row.campaign_name,
             "channel": row.channel, "start_at": row.start_at.isoformat()} for row in db.scalars(select(Campaign)).all()]


@router.post("/campaigns/{campaign_id}/dial")
def dial_campaign(campaign_id: str, request: DialRequest, db: Session = Depends(get_db)):
    try:
        return allocator.start_campaign(
            db, campaign_id, request.mode, request.provider, request.max_calls,
            request.answer_rate, request.average_call_duration_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Dial request could not be completed.") from exc


@router.get("/agents")
def list_agents(limit: int = 100, db: Session = Depends(get_db)):
    if not 1 <= limit <= 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000.")
    rows = db.execute(select(Agent, AgentRuntimeState.state).outerjoin(
        AgentRuntimeState, Agent.agent_id == AgentRuntimeState.agent_id,
    ).order_by(Agent.agent_id).limit(limit)).all()
    return [{"agent_id": agent.agent_id, "name": agent.agent_name, "work_status": agent.status,
             "dialer_state": state or ("AVAILABLE" if agent.status.upper() == "ACTIVE" else "OFFLINE")}
            for agent, state in rows]


@router.put("/agents/{agent_id}/state")
def update_agent_state(agent_id: str, request: AgentStateUpdate, db: Session = Depends(get_db)):
    try:
        state = set_agent_state(db, agent_id, AgentState(request.state))
        db.commit()
        return {"agent_id": agent_id, "state": state.state}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/borrowers")
def list_borrowers(limit: int = 100, db: Session = Depends(get_db)):
    if not 1 <= limit <= 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000.")
    return [{"borrower_id": row.borrower_id, "name": row.name, "city": row.city}
            for row in db.scalars(select(Borrower).order_by(Borrower.borrower_id).limit(limit)).all()]


@router.get("/calls")
def list_calls(limit: int = 100, db: Session = Depends(get_db)):
    if not 1 <= limit <= 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000.")
    dialer_calls = db.scalars(select(DialerCall).order_by(DialerCall.created_at.desc()).limit(limit)).all()
    result = [allocator.call_to_dict(row) for row in dialer_calls]
    if len(result) < limit:
        historical = db.scalars(select(Call).order_by(Call.event_at.desc()).limit(limit - len(result))).all()
        result.extend({"call_id": row.call_id, "campaign_id": row.campaign_id, "borrower_id": row.borrower_id,
                       "agent_id": row.agent_id, "provider": "dataset", "state": row.call_status,
                       "created_at": row.event_at.isoformat(), "updated_at": row.event_at.isoformat()}
                      for row in historical)
    return result


@router.post("/calls/{call_id}/events")
def receive_provider_event(call_id: str, request: ProviderEventRequest, db: Session = Depends(get_db)):
    from ..providers import ProviderEventData

    try:
        changed = allocator.apply_provider_event(
            db, call_id, request.provider,
            ProviderEventData(event_id=request.event_id, event_type=request.event_type),
        )
        return {"accepted": True, "state_changed": changed}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    return collect_metrics(db)


@router.post("/simulation/run")
def run_simulation(request: SimulationRequest, campaign_id: str, db: Session = Depends(get_db)):
    try:
        return SimulationEngine(allocator).run(db, campaign_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/simulation/recover")
def recover_worker_crash(timeout_seconds: int = 60, db: Session = Depends(get_db)):
    if not 1 <= timeout_seconds <= 86400:
        raise HTTPException(status_code=422, detail="timeout_seconds must be between 1 and 86400.")
    return {"recovered_calls": recover_stale_calls(db, timeout_seconds)}
