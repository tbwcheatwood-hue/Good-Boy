"""Deterministic recovery for malformed local-model tool calls.

Small models wrap JSON in markdown, invent parameter names, or stop halfway
through a call. This module repairs the cases that are unambiguous and asks
the model to correct itself at most twice. The third failure is a short
message for the user, not another silent retry.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MAX_TOOL_REPAIR_RETRIES = 2

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_PARAM_ALIASES = {
    "file": "path",
    "filename": "path",
    "filepath": "path",
    "file_path": "path",
    "text": "content",
    "body": "content",
    "message": "content",
    "query_string": "query",
    "search": "query",
    "search_query": "query",
}

_RETRY = (
    "The previous tool call was not valid JSON. Reply with ONE tool call only: "
    "a JSON object {\"name\": \"<registered tool>\", \"arguments\": { ... }} "
    "using the tool's real parameter names. No markdown."
)
_ESCALATE = (
    "I couldn't turn that into a working action after two tries. "
    "Say it again in one sentence and I'll do it."
)


@dataclass(frozen=True, slots=True)
class ToolRepairPlan:
    calls: tuple[dict[str, Any], ...] = ()
    retry_prompt: str | None = None
    escalate: bool = False
    user_message: str | None = None


def looks_like_tool_attempt(text: str) -> bool:
    if not text or "{" not in text:
        return False
    lowered = text.lower()
    return (
        "```" in text
        or '"name"' in lowered
        or '"arguments"' in lowered
        or '"tool"' in lowered
    )


def _tool_schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "schema", None)
    if isinstance(schema, dict):
        return schema
    if isinstance(tool, dict):
        raw = tool.get("schema") or tool.get("input_schema") or {}
        return raw if isinstance(raw, dict) else {}
    return {}


def _properties(tool: Any) -> set[str]:
    props = _tool_schema(tool).get("properties") or {}
    if isinstance(props, dict):
        return {str(key) for key in props}
    return set()


def _loads(fragment: str) -> Any:
    try:
        return json.loads(fragment)
    except json.JSONDecodeError:
        repaired = fragment.replace("'", '"')
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        return json.loads(repaired)


def _candidate_fragment(text: str) -> str | None:
    fenced = _FENCE_RE.search(text)
    if fenced:
        return fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return None


def _align_arguments(name: str, arguments: dict[str, Any], tools: Mapping[str, Any]) -> dict[str, Any]:
    allowed = _properties(tools.get(name))
    if not allowed:
        return dict(arguments)
    aligned: dict[str, Any] = {}
    for key, value in arguments.items():
        if key in allowed:
            aligned[key] = value
            continue
        canonical = _PARAM_ALIASES.get(key)
        if canonical and canonical in allowed and canonical not in aligned:
            aligned[canonical] = value
    return aligned


def plan_tool_repair(
    text: str,
    *,
    attempt: int,
    tools: Mapping[str, Any],
) -> ToolRepairPlan:
    """Recover one call, ask for a retry, or escalate to the user.

    ``attempt`` is how many repair prompts have already been sent this turn.
    A valid call on the last attempt is accepted. Escalation happens only
    when that attempt is still not a usable call.
    """
    fragment = _candidate_fragment(text or "")
    def _give_up() -> ToolRepairPlan:
        if attempt >= MAX_TOOL_REPAIR_RETRIES:
            return ToolRepairPlan(escalate=True, user_message=_ESCALATE)
        return ToolRepairPlan(retry_prompt=_RETRY)

    if not fragment:
        return _give_up()
    try:
        payload = _loads(fragment)
    except json.JSONDecodeError:
        return _give_up()
    if not isinstance(payload, dict):
        return _give_up()
    name = payload.get("name") or payload.get("tool")
    if not isinstance(name, str) or not name.strip():
        return _give_up()
    name = name.strip()
    if name not in tools:
        return _give_up()
    raw_args = payload.get("arguments", payload.get("args", payload.get("input", {})))
    if isinstance(raw_args, str):
        try:
            raw_args = _loads(raw_args)
        except json.JSONDecodeError:
            return _give_up()
    if raw_args is None:
        raw_args = {}
    if not isinstance(raw_args, dict):
        return _give_up()
    arguments = _align_arguments(name, raw_args, tools)
    if not arguments and _properties(tools.get(name)):
        # A name with no usable parameters is a partial call.
        return _give_up()
    return ToolRepairPlan(
        calls=(
            {
                "id": f"repaired_{attempt}_{name}",
                "name": name,
                "input": arguments,
            },
        )
    )
