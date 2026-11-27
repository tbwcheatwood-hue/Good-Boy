"""Ask before creating a reminder when the person was only thinking out loud.

"I should probably check on that build tomorrow" is not "Sam, set a reminder
for tomorrow at 9 AM". Ambiguous phrasing must confirm. An explicit command
may proceed.
"""

from __future__ import annotations

import re

_EXPLICIT = re.compile(
    r"\b("
    r"set (a |an )?(reminder|alarm|timer)|"
    r"remind me|"
    r"add (a |an )?(reminder|alarm)|"
    r"create (a |an )?(reminder|routine)|"
    r"schedule (a |an )?(reminder|routine)"
    r")\b",
    re.IGNORECASE,
)
_AMBIGUOUS = re.compile(
    r"\b("
    r"i should|"
    r"i ought|"
    r"i might|"
    r"i'll probably|"
    r"i will probably|"
    r"probably|"
    r"maybe|"
    r"at some point|"
    r"sometime|"
    r"when i get a chance"
    r")\b",
    re.IGNORECASE,
)
_ROUTINE_TOOL = ("remind", "routine", "schedule", "cron")


def classify_routine_utterance(text: str) -> str:
    """``explicit``, ``ambiguous``, or ``none``."""
    utterance = text or ""
    if _EXPLICIT.search(utterance):
        return "explicit"
    if _AMBIGUOUS.search(utterance):
        return "ambiguous"
    return "none"


def needs_routine_confirmation(tool_name: str, utterance: str) -> bool:
    """True when a routine-creating tool must stop and ask."""
    name = (tool_name or "").lower()
    if not any(token in name for token in _ROUTINE_TOOL):
        return False
    return classify_routine_utterance(utterance) == "ambiguous"
