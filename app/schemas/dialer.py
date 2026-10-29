from typing import Literal

from pydantic import BaseModel, Field


class DialRequest(BaseModel):
    mode: Literal["progressive", "predictive"] = "progressive"
    provider: Literal["provider_a", "provider_b"] = "provider_a"
    max_calls: int = Field(default=100, ge=1, le=5000)
    answer_rate: float = Field(default=0.5, ge=0, le=1)
    average_call_duration_seconds: float = Field(default=120, gt=0)


class AgentStateUpdate(BaseModel):
    state: Literal["AVAILABLE", "OFFLINE", "PAUSED"]


class ProviderEventRequest(BaseModel):
    provider: Literal["provider_a", "provider_b"]
    event_id: str = Field(min_length=1, max_length=100)
    event_type: Literal["RINGING", "ANSWERED", "CONNECTED", "COMPLETED", "FAILED", "CANCELLED"]


class SimulationRequest(DialRequest):
    ticks: int = Field(default=5, ge=1, le=100)
