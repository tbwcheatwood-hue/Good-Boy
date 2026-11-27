"""Mic gating while the assistant's own speakers are active.

Half-duplex drops microphone frames for the whole time playback is audible.
A headset or a hardware echo canceller can set a barge-in energy override:
a frame at least that loud is kept, so the person can still interrupt.
"""

from __future__ import annotations


def drop_mic_during_playback(
    *,
    half_duplex: bool,
    playback: bool,
    energy: float = 0.0,
    barge_in_energy: float = 0.0,
) -> bool:
    """True when this microphone frame must not become a user turn."""
    if not half_duplex or not playback:
        return False
    if barge_in_energy > 0 and energy >= barge_in_energy:
        return False
    return True
