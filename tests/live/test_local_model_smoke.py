"""Opt-in smoke against a local model server.

    GOOD_BOY_LIVE_LOCAL=1 pytest -m live_local

Skipped unless that variable is set, so a normal run never calls a model.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.live_local


def test_live_local_smoke_is_opt_in() -> None:
    if os.environ.get("GOOD_BOY_LIVE_LOCAL") != "1":
        pytest.skip("set GOOD_BOY_LIVE_LOCAL=1 to call a local model server")
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "live_local_smoke.py"
    spec = importlib.util.spec_from_file_location("live_local_smoke", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0
