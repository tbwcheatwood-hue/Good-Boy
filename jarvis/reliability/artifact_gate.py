"""A reviewer cannot call a file done unless it is really on disk and parses.

Python is checked with the stdlib parser. JSON is checked with the stdlib
decoder. Other files must exist and be non-empty. Untrusted mission output
is never executed.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path


def artifact_ok(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "file does not exist"
    try:
        size = path.stat().st_size
    except OSError as exc:
        return False, f"cannot stat file: {exc.__class__.__name__}"
    if size <= 0:
        return False, "file is empty"
    suffix = path.suffix.lower()
    if suffix == ".py":
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError) as exc:
            return False, f"python syntax check failed: {exc.__class__.__name__}"
        return True, "python syntax ok"
    if suffix == ".json":
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            return False, f"json parse failed: {exc.__class__.__name__}"
        return True, "json ok"
    return True, "present"
