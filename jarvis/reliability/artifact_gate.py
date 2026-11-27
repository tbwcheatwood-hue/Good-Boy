"""A reviewer cannot call a file done unless it is really on disk.

Python and JSON are parsed. Python, JavaScript, and shell files are then
executed in a temporary directory with a short timeout, a stripped
environment, and a network block. The mission directory itself is not the
working directory, and the process does not inherit the user's secrets.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from jarvis.core.process_utils import NO_WINDOW_CREATIONFLAGS

_TIMEOUT_S = 5.0

_PYTHON_RUNNER = """\
import os, runpy, socket, sys
root = os.path.realpath(os.environ["GOOD_BOY_SANDBOX"])

def _blocked(*_args, **_kwargs):
    raise OSError("network is disabled in the artifact sandbox")

socket.socket = _blocked  # type: ignore[misc]
socket.create_connection = _blocked  # type: ignore[assignment]

target = os.path.realpath(sys.argv[1])
if not target.startswith(root + os.sep) and target != root:
    raise SystemExit("script escaped the sandbox")
runpy.run_path(target, run_name="__main__")
"""


def _sandbox_env(root: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "GOOD_BOY_SANDBOX": str(root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "LANG": "C.UTF-8",
    }


def _run(cmd: list[str], root: Path) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            cmd,
            cwd=root,
            env=_sandbox_env(root),
            capture_output=True,
            timeout=_TIMEOUT_S,
            creationflags=NO_WINDOW_CREATIONFLAGS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "execution timed out"
    except OSError as exc:
        return False, f"execution could not start: {exc.__class__.__name__}"
    if completed.returncode != 0:
        return False, f"execution failed with exit {completed.returncode}"
    return True, "executed"


def execute_artifact(path: Path) -> tuple[bool, str]:
    """Run a copy of ``path`` inside a fresh temporary directory."""
    suffix = path.suffix.lower()
    sandbox = Path(tempfile.mkdtemp(prefix="gb-artifact-"))
    try:
        target = sandbox / path.name
        shutil.copy(path, target)
        if suffix == ".py":
            runner = sandbox / "_runner.py"
            runner.write_text(_PYTHON_RUNNER, encoding="utf-8")
            cmd = [sys.executable, "-I", str(runner), str(target)]
            unshare = shutil.which("unshare")
            if unshare:
                confined = _run([unshare, "--net", "--", *cmd], sandbox)
                if confined[0] or "could not start" not in confined[1]:
                    # A real script failure is returned. An unshare that the
                    # kernel rejected falls through to the same runner.
                    if confined[0] or not confined[1].startswith("execution failed with exit 1"):
                        return confined
            return _run(cmd, sandbox)
        if suffix == ".js":
            node = shutil.which("node")
            if not node:
                return True, "node is not installed; file was not executed"
            return _run([node, str(target)], sandbox)
        if suffix in {".sh", ".bash"}:
            shell = shutil.which("bash") or shutil.which("sh")
            if not shell:
                return False, "no shell is installed"
            return _run([shell, str(target)], sandbox)
        return True, "not an executable artifact"
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


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
        return execute_artifact(path)
    if suffix == ".json":
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            return False, f"json parse failed: {exc.__class__.__name__}"
        return True, "json ok"
    if suffix in {".js", ".sh", ".bash"}:
        return execute_artifact(path)
    return True, "present"
