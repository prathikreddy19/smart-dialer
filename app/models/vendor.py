from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from ..database.database import Base


class Vendor(Base):
    __tablename__ = "vendors"

    vendor_id = Column(String(20), primary_key=True, index=True)

    vendor_name = Column(String(100), nullable=False)

    vendor_account_id = Column(String(50), nullable=False)

    timezone = Column(String(50), nullable=False)

    status = Column(String(20), nullable=False)

    schema_version = Column(String(20), nullable=False)

    # Relationships
    agents = relationship(
        "Agent",
        back_populates="vendor"
    )

    calls = relationship(
        "Call",
        back_populates="vendor"
    )

    call_attempts = relationship(
        "CallAttempt",
        back_populates="vendor"
    )
