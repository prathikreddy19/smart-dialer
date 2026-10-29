from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.dialects import mysql

from app.database.database import SessionLocal
from app.models import Agent, AgentRuntimeState, Borrower, Campaign, DialerCall, ProviderEvent, Vendor
from app.providers import MockProviderB, ProviderEventData, ProviderRegistry
from app.services.call_allocator import CallAllocator, recover_stale_calls, set_agent_state
from app.state_machine import AgentState, CallState


def seed(db: Session, agents: int = 1, borrowers: int = 3) -> None:
    now = datetime(2025, 1, 1)
    db.add(Vendor(vendor_id="V1", vendor_name="Vendor", vendor_account_id="ACC", timezone="UTC",
                  status="ACTIVE", schema_version="1"))
    db.add(Campaign(campaign_id="C1", campaign_name="Test", channel="VOICE", strategy_version="1",
                    start_at=now, target_definition="all"))
    for idx in range(agents):
        db.add(Agent(agent_id=f"A{idx}", employee_code=f"E{idx}", agent_name="Agent", vendor_id="V1",
                     team="T", status="ACTIVE", joined_at=now, updated_at=now))
    for idx in range(borrowers):
        db.add(Borrower(borrower_id=f"B{idx}", name="Borrower", phone=None, email=None, city=None,
                        created_at=now, updated_at=now, state="CA"))
    db.commit()


def test_progressive_allocator_never_allocates_more_calls_than_agents():
    db = SessionLocal()
    try:
        seed(db, agents=1, borrowers=5)
        result = CallAllocator(ProviderRegistry()).start_campaign(db, "C1", "progressive", max_calls=5)
        assert result["initiated_calls"] == 1
        assert result["initiated_calls"] <= 1
        call = db.query(DialerCall).one()
        assert call.agent_id == "A0"
    finally:
        db.close()


def test_reserved_agent_is_not_reallocated():
    db = SessionLocal()
    try:
        seed(db, agents=1, borrowers=5)
        db.add(AgentRuntimeState(agent_id="A0", state=AgentState.RESERVED.value, updated_at=datetime.utcnow()))
        db.commit()
        result = CallAllocator(ProviderRegistry()).start_campaign(db, "C1", "progressive")
        assert result["initiated_calls"] == 0
    finally:
        db.close()


def test_reservation_query_supports_mysql_skip_locked():
    query = select(Agent).with_for_update(skip_locked=True)
    sql = str(query.compile(dialect=mysql.dialect())).upper()
    assert "FOR UPDATE SKIP LOCKED" in sql


def test_predictive_recommendation_cannot_bypass_agent_capacity():
    db = SessionLocal()
    try:
        seed(db, agents=1, borrowers=5)
        result = CallAllocator(ProviderRegistry()).start_campaign(
            db, "C1", "predictive", max_calls=50, answer_rate=0.1,
        )
        assert result["recommended_calls"] > result["initiated_calls"]
        assert result["initiated_calls"] == 1
    finally:
        db.close()


def test_duplicate_provider_event_is_idempotent_and_completion_wins():
    db = SessionLocal()
    try:
        seed(db)
        now = datetime.utcnow()
        db.add(AgentRuntimeState(agent_id="A0", state=AgentState.DIALING.value, updated_at=now))
        call = DialerCall(call_id="CALL-1", campaign_id="C1", borrower_id="B0", agent_id="A0",
                          provider="provider_b", state=CallState.INITIATED.value, created_at=now, updated_at=now)
        db.add(call)
        db.commit()
        allocator = CallAllocator(ProviderRegistry())
        assert allocator.apply_provider_event(db, "CALL-1", "provider_b", ProviderEventData("evt-1", "COMPLETED"))
        assert not allocator.apply_provider_event(db, "CALL-1", "provider_b", ProviderEventData("evt-1", "ANSWERED"))
        assert db.query(DialerCall).one().state == CallState.COMPLETED.value
        assert db.query(ProviderEvent).count() == 1
        assert db.get(AgentRuntimeState, "A0").state == AgentState.AVAILABLE.value
    finally:
        db.close()


def test_agent_availability_drop_cancels_setup_call():
    db = SessionLocal()
    try:
        seed(db)
        now = datetime.utcnow()
        db.add(AgentRuntimeState(agent_id="A0", state=AgentState.DIALING.value, updated_at=now))
        db.add(DialerCall(call_id="CALL-2", campaign_id="C1", borrower_id="B0", agent_id="A0",
                          provider="provider_a", state=CallState.INITIATED.value, created_at=now, updated_at=now))
        db.commit()
        runtime = set_agent_state(db, "A0", AgentState.OFFLINE)
        db.commit()
        assert runtime.state == AgentState.OFFLINE.value
        assert db.query(DialerCall).one().state == CallState.CANCELLED.value
    finally:
        db.close()


def test_stale_setup_recovery_cancels_call_and_releases_agent():
    db = SessionLocal()
    try:
        seed(db)
        old = datetime.utcnow() - timedelta(minutes=5)
        db.add(AgentRuntimeState(agent_id="A0", state=AgentState.DIALING.value, updated_at=old))
        db.add(DialerCall(call_id="CALL-3", campaign_id="C1", borrower_id="B0", agent_id="A0",
                          provider="provider_a", state=CallState.INITIATED.value, created_at=old, updated_at=old))
        db.commit()
        assert recover_stale_calls(db, timeout_seconds=30) == 1
        assert db.query(DialerCall).one().state == CallState.CANCELLED.value
        assert db.get(AgentRuntimeState, "A0").state == AgentState.AVAILABLE.value
    finally:
        db.close()


def test_provider_b_times_out_and_emits_duplicate_out_of_order_events():
    timeout_provider = MockProviderB(seed=1)
    try:
        timeout_provider.place_call("C1", answer_rate=1)
    except TimeoutError:
        pass
    else:
        raise AssertionError("seeded provider should exercise its timeout path")
    assert timeout_provider.timeouts == 1

    event_provider = MockProviderB(seed=2)
    events = event_provider.place_call("C2", answer_rate=0)
    assert events[0].event_type == "FAILED"
    assert events[1].event_id == events[2].event_id
    assert events[-1].event_type == "RINGING"
