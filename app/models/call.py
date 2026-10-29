from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database.database import Base


class Call(Base):
    __tablename__ = "calls"

    call_id = Column(String(20), primary_key=True, index=True)

    account_id = Column(String(20), nullable=False, index=True)

    borrower_id = Column(
        String(20),
        ForeignKey("borrowers.borrower_id"),
        nullable=False,
        index=True,
    )

    agent_id = Column(
        String(20),
        ForeignKey("agents.agent_id"),
        nullable=True,
        index=True,
    )

    campaign_id = Column(
        String(20),
        ForeignKey("campaigns.campaign_id"),
        nullable=False,
        index=True,
    )

    vendor_id = Column(
        String(20),
        ForeignKey("vendors.vendor_id"),
        nullable=False,
        index=True,
    )

    event_at = Column(DateTime, nullable=False)

    direction = Column(String(20), nullable=False)

    call_status = Column(String(30), nullable=False)

    duration_sec = Column(Integer, nullable=True)

    timezone = Column(String(50), nullable=False)

    # Relationships
    borrower = relationship(
        "Borrower",
        back_populates="calls"
    )

    agent = relationship(
        "Agent",
        back_populates="calls"
    )

    campaign = relationship(
        "Campaign",
        back_populates="calls"
    )

    vendor = relationship(
        "Vendor",
        back_populates="calls"
    )

    call_attempts = relationship(
        "CallAttempt",
        back_populates="call",
        cascade="all, delete-orphan"
    )
