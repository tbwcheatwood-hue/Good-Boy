"""Sliding-window compaction when a small context window is near saturation.

Local 4k/8k models are primary citizens. Once the estimated prompt crosses
85% of the window, older conversational turns move into a short scratchpad
note. System messages and any turn that carries a security or risk-tier rule
stay verbatim.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

_CHARS_PER_TOKEN = 3
_DEFAULT_SATURATION = 0.85
_SHORT_NOTE = (
    "[scratchpad] Earlier turns were compacted to fit the context window. "
    "Security and system rules were kept verbatim."
)
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


def _body(messages: Sequence[Any], system_text: str) -> str:
    return system_text + "".join(_text(message) for message in messages)


def estimate_tokens(
    messages: Sequence[Any], system_text: str = "", *, model: str = ""
) -> int:
    """Token estimate. Uses tiktoken when it is installed, else a conservative count.

    Local GGUF models do not share one tokenizer. The character fallback uses
    3 characters per token, which over-counts English and so stays under a
    small context window instead of overflowing it. ``model`` is accepted so
    a caller can name the model; unknown ids still use cl100k when tiktoken
    is present.
    """
    _ = model
    body = _body(messages, system_text)
    if not body:
        return 1
    try:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        counted = len(encoding.encode(body))
        # Quantized local models tokenize less efficiently than this encoding.
        return max(1, int(counted * 1.15) + 1)
    except Exception:  # noqa: BLE001 — missing tokenizer must not break a turn
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


def _groups(items: list[Any]) -> list[list[Any]]:
    """Keep an assistant tool call with the tool results that follow it."""
    groups: list[list[Any]] = []
    index = 0
    while index < len(items):
        if _role(items[index]) == "assistant":
            end = index + 1
            while end < len(items) and _role(items[end]) == "tool":
                end += 1
            groups.append(items[index:end])
            index = end
            continue
        groups.append([items[index]])
        index += 1
    return groups


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
    groups = _groups(items)

    def flat() -> list[Any]:
        return [message for group in groups for message in group]

    budget = max(1, int(context_window * saturation))
    if estimate_tokens(flat(), system_text) <= budget:
        return flat()

    dropped: list[str] = []
    # Walk from the oldest droppable group. Never drop the last group.
    # A tool call and its results drop together so a result is not left
    # without the call that produced it.
    while estimate_tokens(flat(), system_text) > budget and len(groups) > 1:
        drop_at = next(
            (
                index
                for index, group in enumerate(groups[:-1])
                if not any(_protected(message) for message in group)
            ),
            None,
        )
        if drop_at is None:
            break
        snippet = " ".join(_text(groups[drop_at][0]).split())[:160]
        if snippet:
            dropped.append(snippet)
        del groups[drop_at]
    items = flat()

    if dropped:
        note = (
            "[scratchpad] Earlier turns were compacted to fit a "
            f"{context_window}-token window. Kept security and system rules "
            "verbatim. Dropped turns, oldest first: " + " | ".join(dropped[:8])
        )
        items.insert(0, _clone_with_content(items[0], note))
        # The note is inserted after the drop loop. If the excerpts themselves
        # push a small window back over the budget, keep a one-line marker.
        # If even that marker does not fit, omit it: the protected messages
        # already consumed the window, and adding text would only make it worse.
        if estimate_tokens(items, system_text) > budget:
            items[0] = _clone_with_content(items[0], _SHORT_NOTE)
        if estimate_tokens(items, system_text) > budget:
            del items[0]
    return items
