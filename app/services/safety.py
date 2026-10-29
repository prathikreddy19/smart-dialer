from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyResult:
    approved_calls: int
    decision: str
    reason: str


class SafetyController:
    """Enforces the hard one-agent-per-call limit after any pacing recommendation."""

    def evaluate(
        self, recommended: int, available_agents: int, queued_borrowers: int,
        provider_health: float, predictive: bool = False,
    ) -> SafetyResult:
        if min(recommended, available_agents, queued_borrowers) < 0:
            raise ValueError("Counts cannot be negative.")
        if provider_health < 0.5:
            return SafetyResult(0, "REJECTED", "Provider health is below the 50% safety threshold.")
        capacity = min(available_agents, queued_borrowers)
        if predictive and provider_health < 0.75 and capacity:
            return SafetyResult(capacity, "FALLBACK_PROGRESSIVE", "Provider health is reduced; using one call per available agent.")
        approved = min(recommended, capacity)
        if approved == 0:
            return SafetyResult(0, "REJECTED", "No available agent or eligible borrower.")
        if approved < recommended:
            return SafetyResult(approved, "REDUCED", "Reduced to one call per available agent and eligible borrower.")
        return SafetyResult(approved, "APPROVED", "One agent is reserved for every approved call.")
