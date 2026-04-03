"""Tiny animation helper for smooth card transitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Tween:
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    duration: float
    elapsed: float = 0.0

    def step(self, dt: float) -> tuple[float, float, bool]:
        """Advance tween and return (x, y, finished)."""
        self.elapsed = min(self.duration, self.elapsed + dt)
        if self.duration <= 0:
            return self.end_x, self.end_y, True
        t = self.elapsed / self.duration
        # Ease out cubic for polished movement.
        t = 1 - (1 - t) ** 3
        x = self.start_x + (self.end_x - self.start_x) * t
        y = self.start_y + (self.end_y - self.start_y) * t
        return x, y, self.elapsed >= self.duration
