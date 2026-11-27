"""Keep a local brain on local hardware when the endpoint is cold or busy.

Ollama, LM Studio, and llama.cpp answer 503 while a model is loading and 429
when the local queue is full. That is not permission to spend a cloud API key.
Paid providers stay off the chain unless the user explicitly opted in.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

# Mirrors jarvis.costs.model.LOCAL_PROVIDERS, plus the quantized runtimes the
# Phase-2 audit treats as primary citizens. Matched on the provider id.
LOCAL_PROVIDER_IDS = frozenset(
    {
        "local",
        "local-realtime",
        "local-voice",
        "local-openai",
        "ollama",
        "llamacpp",
        "llama-cpp",
        "llama.cpp",
        "lmstudio",
        "lm-studio",
        "vllm",
        "mlx",
        "exl2",
        "whisper-local",
    }
)


def is_local_provider(name: str | None) -> bool:
    if not name:
        return False
    key = name.strip().lower()
    return key in LOCAL_PROVIDER_IDS or key.startswith("local-")


def paid_fallback_allowed(explicit: bool = False) -> bool:
    """True only when the caller opted in, or the process env says so."""
    if explicit:
        return True
    flag = os.environ.get("GOOD_BOY_ALLOW_PAID_FALLBACK", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def restrict_paid_fallback(
    active: str,
    chain: Sequence[tuple[str, str | None]],
    *,
    allow_paid: bool = False,
) -> list[tuple[str, str | None]]:
    """Drop non-local hops when the active brain is a local runtime.

    A cloud-primary chain is unchanged. When every configured hop was paid,
    the active local provider is kept alone so the turn fails honestly instead
    of billing a key.
    """
    items = list(chain)
    if paid_fallback_allowed(allow_paid) or not is_local_provider(active):
        return items
    kept = [item for item in items if is_local_provider(item[0])]
    if kept:
        return kept
    return [(active, None)]
