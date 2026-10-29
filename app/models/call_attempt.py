from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database.database import Base


class CallAttempt(Base):
    __tablename__ = "call_attempts"

    attempt_id = Column(String(20), primary_key=True, index=True)

    account_id = Column(String(20), nullable=False, index=True)

    borrower_id = Column(
        String(20),
        ForeignKey("borrowers.borrower_id"),
        nullable=False,
        index=True,
    )

    call_id = Column(
        String(20),
        ForeignKey("calls.call_id"),
        nullable=False,
        index=True,
    )

    agent_id = Column(
        String(20),
        ForeignKey("agents.agent_id"),
        nullable=False,
        index=True,
    )

    vendor_id = Column(
        String(20),
        ForeignKey("vendors.vendor_id"),
        nullable=True,
        index=True,
    )

    event_at = Column(DateTime, nullable=False)

    attempt_no = Column(Integer, nullable=False)

    attempt_status = Column(String(30), nullable=False)

    # Relationships
    borrower = relationship(
        "Borrower",
        back_populates="call_attempts"
    )

    call = relationship(
        "Call",
        back_populates="call_attempts"
    )

    agent = relationship(
        "Agent",
        back_populates="call_attempts"
    )

    vendor = relationship(
        "Vendor",
        back_populates="call_attempts"
    )
