"""Stop a crew from bouncing the same failure forever.

Architect/developer ping-pong and a debugger retrying one identical test
share a fingerprint. After ``limit`` identical failures the loop stops and
the person gets a plain escalation instead of another automatic retry.
"""

from __future__ import annotations

from collections import Counter


class FailureCircuit:
    def __init__(self, limit: int = 2) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self.limit = limit
        self._counts: Counter[str] = Counter()

    def allow(self, fingerprint: str) -> bool:
        """Record one failure. False means the loop must escalate now."""
        key = " ".join((fingerprint or "unknown").split())[:240] or "unknown"
        self._counts[key] += 1
        return self._counts[key] <= self.limit

    @staticmethod
    def escalation_message(fingerprint: str) -> str:
        short = " ".join((fingerprint or "the same failure").split())[:180]
        return (
            "Stopping this crew loop. The same failure happened again "
            f"({short}). It needs a person to look at the worktree before "
            "another attempt."
        )
