"""Phase-2 reliability guards for small local models, voice, crew, and trust boundaries.

These helpers are pure and side-effect free. Call sites in the brain, missions,
and hardware probes apply them; they do not replace those subsystems.
"""

from jarvis.reliability.acoustic import effective_wake_threshold, phantom_transcript
from jarvis.reliability.artifact_gate import artifact_ok
from jarvis.reliability.context_pressure import compact_messages
from jarvis.reliability.crew import FailureCircuit
from jarvis.reliability.intent import needs_routine_confirmation
from jarvis.reliability.local_failover import restrict_paid_fallback
from jarvis.reliability.sandbox import path_is_inside, sensitive_relative
from jarvis.reliability.soul_guard import personality_drift
from jarvis.reliability.telemetry import collect_telemetry
from jarvis.reliability.tool_repair import plan_tool_repair
from jarvis.reliability.untrusted import exfil_blocked, untrusted_instruction

__all__ = [
    "FailureCircuit",
    "artifact_ok",
    "collect_telemetry",
    "compact_messages",
    "effective_wake_threshold",
    "exfil_blocked",
    "needs_routine_confirmation",
    "path_is_inside",
    "personality_drift",
    "phantom_transcript",
    "plan_tool_repair",
    "restrict_paid_fallback",
    "sensitive_relative",
    "untrusted_instruction",
]
