"""Stage timings for push-to-talk: release → STT → first token → audio start.

The timeline is a measurement, not a second audio thread. Callers mark the
boundaries they actually crossed and read the slowest stage.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PttLatency:
    stages_ms: dict[str, float]
    total_ms: float
    slowest: str

    def line(self) -> str:
        parts = [f"{name}={ms:.0f}ms" for name, ms in self.stages_ms.items()]
        return f"ptt {self.total_ms:.0f}ms (" + ", ".join(parts) + f") slowest={self.slowest}"


class PttTimeline:
    def __init__(self) -> None:
        self._marks: list[tuple[str, float]] = [("release", time.monotonic())]

    def mark(self, name: str) -> None:
        self._marks.append((name, time.monotonic()))

    def finish(self) -> PttLatency:
        if len(self._marks) < 2:
            return PttLatency(stages_ms={}, total_ms=0.0, slowest="")
        stages: dict[str, float] = {}
        slowest = ""
        slowest_ms = -1.0
        for (left, t0), (right, t1) in zip(self._marks, self._marks[1:]):
            ms = max(0.0, (t1 - t0) * 1000.0)
            label = f"{left}->{right}"
            stages[label] = ms
            if ms > slowest_ms:
                slowest = label
                slowest_ms = ms
        total = (self._marks[-1][1] - self._marks[0][1]) * 1000.0
        return PttLatency(stages_ms=stages, total_ms=total, slowest=slowest)
