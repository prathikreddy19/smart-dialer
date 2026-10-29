from dataclasses import dataclass
import random
import time
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class ProviderEventData:
    event_id: str
    event_type: str


class TelecomProvider(Protocol):
    name: str
    health: float

    def place_call(self, call_id: str, answer_rate: float) -> list[ProviderEventData]: ...


class MockProviderA:
    name = "provider_a"
    latency_seconds = 0.01

    def __init__(self, seed: int = 1) -> None:
        self.random = random.Random(seed)
        self.attempts = self.timeouts = self.failures = self.connected = 0

    @property
    def health(self) -> float:
        return (self.attempts - self.failures + 2) / (self.attempts + 2)

    def place_call(self, call_id: str, answer_rate: float) -> list[ProviderEventData]:
        time.sleep(self.latency_seconds)
        self.attempts += 1
        if self.random.random() < 0.02:
            self.failures += 1
            return [_event("FAILED")]
        if self.random.random() >= answer_rate:
            return [_event("RINGING"), _event("FAILED")]
        self.connected += 1
        return [_event(name) for name in ("RINGING", "ANSWERED", "CONNECTED", "COMPLETED")]


class MockProviderB:
    name = "provider_b"
    latency_seconds = 0.08

    def __init__(self, seed: int = 7) -> None:
        self.random = random.Random(seed)
        self.attempts = self.timeouts = self.failures = self.connected = 0

    @property
    def health(self) -> float:
        return (self.attempts - self.failures + 2) / (self.attempts + 2)

    def place_call(self, call_id: str, answer_rate: float) -> list[ProviderEventData]:
        time.sleep(self.latency_seconds)
        self.attempts += 1
        if self.random.random() < 0.15:
            self.timeouts += 1
            self.failures += 1
            raise TimeoutError("Mock Provider B timed out.")
        if self.random.random() >= answer_rate:
            events = [_event("RINGING"), _event("FAILED")]
        else:
            self.connected += 1
            events = [_event(name) for name in ("RINGING", "ANSWERED", "CONNECTED", "COMPLETED")]
        # Simulate duplicate callbacks and occasional late delivery.
        if events:
            events.insert(1, events[0])
        if self.random.random() < 0.2 and len(events) > 1:
            events = list(reversed(events))
        return events


def _event(event_type: str) -> ProviderEventData:
    event_id = str(uuid4())
    return ProviderEventData(event_id=event_id, event_type=event_type)


class ProviderRegistry:
    def __init__(self) -> None:
        self.providers: dict[str, TelecomProvider] = {
            "provider_a": MockProviderA(),
            "provider_b": MockProviderB(),
        }

    def get(self, name: str) -> TelecomProvider:
        try:
            return self.providers[name.casefold()]
        except KeyError as exc:
            raise ValueError(f"Unsupported provider '{name}'. Choose provider_a or provider_b.") from exc

    def metrics(self) -> dict[str, dict[str, int | float]]:
        return {
            name: {
                "attempts": provider.attempts,
                "timeouts": provider.timeouts,
                "failures": provider.failures,
                "connected": provider.connected,
                "health": round(provider.health, 3),
            }
            for name, provider in self.providers.items()
        }


provider_registry = ProviderRegistry()
