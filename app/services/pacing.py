from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PacingInput:
    available_agents: int
    answer_rate: float
    average_call_duration_seconds: float
    provider_health: float = 1.0


@dataclass(frozen=True)
class PacingRecommendation:
    recommended_calls: int
    explanation: str


class PredictivePacingEngine:
    """Suggests a count only; this class has no provider or database dependency."""

    def recommend(self, values: PacingInput) -> PacingRecommendation:
        if values.available_agents < 0 or values.average_call_duration_seconds <= 0:
            raise ValueError("Agent count must be non-negative and call duration must be positive.")
        answer_rate = min(max(values.answer_rate, 0.05), 1.0)
        health = min(max(values.provider_health, 0.0), 1.0)
        if health < 0.5 or values.available_agents == 0:
            return PacingRecommendation(0, "No safe capacity or provider health is below 50%.")
        expected_slots = values.available_agents
        suggestion = math.ceil(expected_slots / answer_rate)
        duration_factor = min(1.0, 180 / values.average_call_duration_seconds)
        suggestion = max(expected_slots, math.ceil(suggestion * duration_factor))
        suggestion = math.floor(suggestion * health)
        return PacingRecommendation(
            max(0, suggestion),
            "Estimate uses open agent slots and answer rate, with a three-minute duration horizon and provider health.",
        )
