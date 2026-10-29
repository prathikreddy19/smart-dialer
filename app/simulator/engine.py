from sqlalchemy.orm import Session

from ..schemas import SimulationRequest
from ..services.call_allocator import CallAllocator
from ..services.metrics import collect_metrics


class SimulationEngine:
    def __init__(self, allocator: CallAllocator) -> None:
        self.allocator = allocator

    def run(self, db: Session, campaign_id: str, request: SimulationRequest) -> dict:
        rounds = []
        for _ in range(request.ticks):
            result = self.allocator.start_campaign(
                db, campaign_id, request.mode, request.provider, request.max_calls,
                request.answer_rate, request.average_call_duration_seconds,
            )
            rounds.append({
                "recommended_calls": result["recommended_calls"],
                "initiated_calls": result["initiated_calls"],
                "safety_decision": result["safety_decision"],
            })
            if result["initiated_calls"] == 0:
                break
        return {"campaign_id": campaign_id, "ticks_run": len(rounds), "runs": rounds,
                "metrics": collect_metrics(db, self.allocator.providers)}
