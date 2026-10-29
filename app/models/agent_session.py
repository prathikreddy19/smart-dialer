from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from ..database.database import Base


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    session_id = Column(String(20), primary_key=True, index=True)

    agent_id = Column(
        String(20),
        ForeignKey("agents.agent_id"),
        nullable=False,
        index=True,
    )

    login_at = Column(DateTime, nullable=False)

    channel = Column(String(50), nullable=False)

    device_id = Column(String(100), nullable=False)

    timezone = Column(String(50), nullable=False)

    logout_at = Column(DateTime, nullable=True)

    # Relationship
    agent = relationship(
        "Agent",
        back_populates="agent_sessions"
    )
