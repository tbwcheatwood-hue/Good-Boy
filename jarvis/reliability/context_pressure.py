"""Sliding-window compaction when a small context window is near saturation.

Local 4k/8k models are primary citizens. Once the estimated prompt crosses
85% of the window, older conversational turns move into a short scratchpad
note. System messages and any turn that carries a security or risk-tier rule
stay verbatim.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

_CHARS_PER_TOKEN = 4
_DEFAULT_SATURATION = 0.85
_PROTECTED_MARKERS = (
    "risk tier",
    "risk-tier",
    "do not follow",
    "ignore previous",
    "security rule",
    "must not",
    "system rule",
)


def _role(message: Any) -> str:
    role = getattr(message, "role", None)
    if role:
        return str(role)
    if isinstance(message, dict):
        return str(message.get("role") or "")
    return ""


def _text(message: Any) -> str:
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("content") or block.get("text") or ""))
            else:
                parts.append(str(block))
        return " ".join(parts)
    return "" if content is None else str(content)


def estimate_tokens(messages: Sequence[Any], system_text: str = "") -> int:
    """Cheap character estimate. Deterministic, no tokenizer dependency."""
    body = system_text + "".join(_text(message) for message in messages)
    return max(1, (len(body) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def _protected(message: Any) -> bool:
    if _role(message) == "system":
        return True
    lowered = _text(message).lower()
    return any(marker in lowered for marker in _PROTECTED_MARKERS)


def _clone_with_content(template: Any, content: str) -> Any:
    """Build a same-type message. Falls back to a plain dict."""
    role = _role(template) or "user"
    if hasattr(template, "role") and hasattr(template, "content"):
        cls = type(template)
        try:
            return cls(role="user", content=content)
        except TypeError:
            pass
    return {"role": role if role == "system" else "user", "content": content}


def compact_messages(
    messages: Sequence[Any],
    *,
    context_window: int,
    system_text: str = "",
    saturation: float = _DEFAULT_SATURATION,
) -> list[Any]:
    """Return messages that fit under ``saturation`` of ``context_window``.

    An unknown or non-positive window is left unchanged. The newest message
    is always kept. Dropped turns are replaced by one scratchpad note so the
    model still knows they happened, without the security rules being summarized
    away — those messages are not eligible to drop.
    """
    items = list(messages)
    if context_window <= 0 or not items:
        return items
    budget = max(1, int(context_window * saturation))
    if estimate_tokens(items, system_text) <= budget:
        return items

    dropped: list[str] = []
    # Walk from the oldest droppable message. Never drop the last message.
    while estimate_tokens(items, system_text) > budget and len(items) > 1:
        drop_at = next(
            (
                index
                for index, message in enumerate(items[:-1])
                if not _protected(message)
            ),
            None,
        )
        if drop_at is None:
            break
        snippet = " ".join(_text(items[drop_at]).split())[:160]
        if snippet:
            dropped.append(snippet)
        del items[drop_at]

    if dropped:
        note = (
            "[scratchpad] Earlier turns were compacted to fit a "
            f"{context_window}-token window. Kept security and system rules "
            "verbatim. Dropped turns, oldest first: " + " | ".join(dropped[:8])
        )
        items.insert(0, _clone_with_content(items[0], note))
    return items
