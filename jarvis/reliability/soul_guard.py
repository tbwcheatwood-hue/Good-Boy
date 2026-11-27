"""Keep learned tone from erasing Sam's character or the risk-tier rules.

SOUL.md may record how the person likes to be addressed. It may not store a
note that makes the assistant sycophantic, unrestricted, or willing to skip
a risk check.
"""

from __future__ import annotations

import re

_DRIFT = re.compile(
    r"("
    r"always agree|"
    r"never disagree|"
    r"never refuse|"
    r"ignore (the )?(safety|risk)|"
    r"skip (the )?(risk|safety|confirm)|"
    r"bypass (the )?(risk|safety|tier)|"
    r"no risk tier|"
    r"without (a )?confirm|"
    r"sycophant|"
    r"flatter (the )?user|"
    r"you are (now )?unrestricted|"
    r"ignore previous"
    r")",
    re.IGNORECASE,
)


def personality_drift(note: str) -> str | None:
    """Why ``note`` must not be written into SOUL.md, or None when it may."""
    text = " ".join((note or "").split())
    if not text:
        return None
    if _DRIFT.search(text):
        return "would erode the grounded character or a risk-tier boundary"
    return None
