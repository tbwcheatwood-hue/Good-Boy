#!/usr/bin/env python3
"""One chat turn against a local server, when one is already running.

Probes Ollama (11434), then an OpenAI-compatible server on 8080 and
LM Studio on 1234. Does nothing to a paid cloud. Exit 0 when no server
is up. Exit 1 when a server answered and the completion failed.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def _get(url: str, timeout: float = 2.0) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except (OSError, urllib.error.URLError):
        return None


def _post(url: str, payload: dict, timeout: float = 60.0) -> dict | None:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None


def main() -> int:
    tags = _get("http://127.0.0.1:11434/api/tags")
    if tags is not None:
        body = json.loads(tags.decode("utf-8"))
        models = body.get("models") or []
        if not models:
            print("Ollama is up and has no models. Nothing was generated.")
            return 0
        name = str(models[0].get("name") or "")
        result = _post(
            "http://127.0.0.1:11434/api/chat",
            {
                "model": name,
                "messages": [{"role": "user", "content": "Reply with the word pong."}],
                "stream": False,
            },
        )
        if not result:
            print(f"Ollama model {name} did not complete a chat.")
            return 1
        print(f"Ollama chat ok: {name}")
        return 0
    for port, label in ((8080, "llama.cpp"), (1234, "LM Studio")):
        models = _get(f"http://127.0.0.1:{port}/v1/models")
        if models is None:
            continue
        parsed = json.loads(models.decode("utf-8"))
        rows = parsed.get("data") or []
        if not rows:
            print(f"{label} is up and has no models.")
            return 0
        name = str(rows[0].get("id") or "")
        result = _post(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            {
                "model": name,
                "messages": [{"role": "user", "content": "Reply with the word pong."}],
                "stream": False,
            },
        )
        if not result:
            print(f"{label} model {name} did not complete a chat.")
            return 1
        print(f"{label} chat ok: {name}")
        return 0
    print("No local Ollama, llama.cpp, or LM Studio server is running.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
