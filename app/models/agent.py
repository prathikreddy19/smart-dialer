from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from ..database.database import Base


class Agent(Base):
    __tablename__ = "agents"

    agent_id = Column(String(20), primary_key=True, index=True)
    employee_code = Column(String(50), nullable=False, index=True)
    agent_name = Column(String(100), nullable=False)
    vendor_id = Column(
        String(20),
        ForeignKey("vendors.vendor_id"),
        nullable=False,
        index=True,
    )
    team = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False)
    joined_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    vendor = relationship("Vendor", back_populates="agents")
    calls = relationship("Call", back_populates="agent")
    call_attempts = relationship("CallAttempt", back_populates="agent")
    agent_sessions = relationship(
        "AgentSession",
        back_populates="agent",
        cascade="all, delete-orphan",
    )
