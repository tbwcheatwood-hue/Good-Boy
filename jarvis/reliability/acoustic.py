"""Speaker-echo guards for wake word and transcripts when there is no hardware AEC.

Playback raises the score a wake model needs, and a transcript that repeats
the line just spoken is dropped. A real barge-in still gets through: the
existing envelope correlator in the realtime path is unchanged, and a loud
wake above the raised bar is accepted.
"""

from __future__ import annotations


def effective_wake_threshold(base: float, *, speakers_active: bool) -> float:
    """Raise the fire bar while the assistant's own speakers are active."""
    if not speakers_active:
        return base
    raised = base + 0.15
    return min(0.95, max(base, raised))


def note_matches_spoken(transcript: str, spoken: str) -> bool:
    """True when the mic mostly played back the line TTS just said."""
    heard = " ".join((transcript or "").lower().split())
    said = " ".join((spoken or "").lower().split())
    if len(heard) < 8 or len(said) < 8:
        return False
    if heard in said or said in heard:
        return True
    heard_words = set(heard.split())
    said_words = set(said.split())
    if not heard_words or not said_words:
        return False
    overlap = len(heard_words & said_words) / len(heard_words)
    return overlap >= 0.8


def phantom_transcript(transcript: str, spoken: str, *, speakers_active: bool) -> bool:
    """Drop a transcript that is the assistant hearing itself."""
    return speakers_active and note_matches_spoken(transcript, spoken)
