from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import relationship

from ..database.database import Base


class Borrower(Base):
    __tablename__ = "borrowers"

    borrower_id = Column(String(20), primary_key=True, index=True)

    name = Column(String(100), nullable=False)

    phone = Column(String(15), nullable=True, index=True)

    email = Column(String(100), nullable=True)

    city = Column(String(100), nullable=True)

    created_at = Column(DateTime, nullable=False)

    updated_at = Column(DateTime, nullable=False)

    state = Column(String(50), nullable=False)

    # Relationships
    calls = relationship(
        "Call",
        back_populates="borrower"
    )

    call_attempts = relationship(
        "CallAttempt",
        back_populates="borrower"
    )
