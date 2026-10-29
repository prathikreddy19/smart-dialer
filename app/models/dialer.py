from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database.database import Base


class AgentRuntimeState(Base):
    __tablename__ = "agent_runtime_states"

    agent_id = Column(String(20), ForeignKey("agents.agent_id"), primary_key=True)
    state = Column(String(20), nullable=False, default="AVAILABLE", index=True)
    updated_at = Column(DateTime, nullable=False)

    agent = relationship("Agent")


class DialerCall(Base):
    __tablename__ = "dialer_calls"

    call_id = Column(String(36), primary_key=True)
    campaign_id = Column(String(20), ForeignKey("campaigns.campaign_id"), nullable=False, index=True)
    borrower_id = Column(String(20), ForeignKey("borrowers.borrower_id"), nullable=False, index=True)
    agent_id = Column(String(20), ForeignKey("agents.agent_id"), nullable=False, index=True)
    provider = Column(String(30), nullable=False)
    state = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    campaign = relationship("Campaign")
    borrower = relationship("Borrower")
    agent = relationship("Agent")
    events = relationship("ProviderEvent", back_populates="call", cascade="all, delete-orphan")


class ProviderEvent(Base):
    __tablename__ = "provider_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_provider_event"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_id = Column(String(36), ForeignKey("dialer_calls.call_id"), nullable=False, index=True)
    provider = Column(String(30), nullable=False)
    event_id = Column(String(100), nullable=False)
    event_type = Column(String(30), nullable=False)
    received_at = Column(DateTime, nullable=False)

    call = relationship("DialerCall", back_populates="events")


class SafetyDecision(Base):
    __tablename__ = "safety_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String(20), ForeignKey("campaigns.campaign_id"), nullable=False, index=True)
    mode = Column(String(20), nullable=False)
    recommended = Column(Integer, nullable=False)
    approved = Column(Integer, nullable=False)
    decision = Column(String(20), nullable=False)
    reason = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False)
