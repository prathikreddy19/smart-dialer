import pytest

from app.services.pacing import PacingInput, PredictivePacingEngine
from app.services.safety import SafetyController


def test_predictive_engine_only_recommends_and_scales_by_answer_rate():
    engine = PredictivePacingEngine()
    conservative = engine.recommend(PacingInput(4, 0.7, 120))
    assert conservative.recommended_calls > 0
    assert "Estimate" in conservative.explanation
    assert engine.recommend(PacingInput(4, 0.7, 120, provider_health=0.2)).recommended_calls == 0
    assert engine.recommend(PacingInput(4, 0.5, 120)).recommended_calls > engine.recommend(
        PacingInput(4, 0.5, 360),
    ).recommended_calls


def test_safety_reduces_predictive_recommendation_to_agent_capacity():
    result = SafetyController().evaluate(recommended=20, available_agents=4, queued_borrowers=10, provider_health=1)
    assert result.approved_calls == 4
    assert result.decision == "REDUCED"


@pytest.mark.parametrize("recommended,agents,borrowers,health", [(-1, 1, 1, 1), (1, -1, 1, 1), (1, 1, -1, 1)])
def test_safety_rejects_negative_inputs(recommended, agents, borrowers, health):
    with pytest.raises(ValueError):
        SafetyController().evaluate(recommended, agents, borrowers, health)


def test_safety_rejects_provider_outage():
    result = SafetyController().evaluate(10, 10, 10, 0.1)
    assert result.approved_calls == 0
    assert result.decision == "REJECTED"


def test_safety_falls_back_to_progressive_when_predictive_provider_health_drops():
    result = SafetyController().evaluate(10, 3, 10, 0.6, predictive=True)
    assert result.approved_calls == 3
    assert result.decision == "FALLBACK_PROGRESSIVE"
