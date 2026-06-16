from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExponentialBackoffConfig:
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    multiplier: float = 2.0
    max_attempts: int | None = None

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt <= 0:
            raise ValueError("attempt must be positive")
        delay = self.initial_delay_seconds * (self.multiplier ** (attempt - 1))
        return min(delay, self.max_delay_seconds)

    def describe_attempts(self) -> str:
        return "unbounded" if self.max_attempts is None else str(self.max_attempts)

