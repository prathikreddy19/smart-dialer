from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import relationship

from ..database.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    campaign_id = Column(String(20), primary_key=True, index=True)

    campaign_name = Column(String(150), nullable=False)

    channel = Column(String(50), nullable=False)

    strategy_version = Column(String(20), nullable=False)

    start_at = Column(DateTime, nullable=False)

    target_definition = Column(String(255), nullable=False)

    end_at = Column(DateTime, nullable=True)

    # Relationships
    calls = relationship(
        "Call",
        back_populates="campaign"
    )
