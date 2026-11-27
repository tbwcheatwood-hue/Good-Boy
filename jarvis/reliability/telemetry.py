"""Hardware telemetry that stays quiet when the vendor tools are absent.

Headless Linux, Windows, and macOS often have no nvidia-smi, rocm-smi, or
powermetrics. Probes must report "unavailable" and return. They must not raise.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass

from jarvis.core.process_utils import NO_WINDOW_CREATIONFLAGS


@dataclass(frozen=True, slots=True)
class HardwareTelemetry:
    ram_total_mb: int | None
    ram_available_mb: int | None
    vram_total_mb: int | None
    vram_source: str
    tokens_per_sec: float | None
    note: str


def _run(argv: list[str], timeout: float = 2.0) -> str:
    if shutil.which(argv[0]) is None:
        return ""
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=NO_WINDOW_CREATIONFLAGS,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (result.stdout or "") + (result.stderr or "")


def _ram() -> tuple[int | None, int | None]:
    try:
        import psutil
    except ImportError:
        return None, None
    try:
        vm = psutil.virtual_memory()
    except Exception:  # noqa: BLE001 — telemetry must not crash the caller
        return None, None
    return vm.total // (1024 * 1024), vm.available // (1024 * 1024)


def _nvidia_vram() -> int | None:
    text = _run(
        ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"]
    )
    total = 0
    found = False
    for line in text.splitlines():
        token = line.strip().split()[0] if line.strip() else ""
        if token.isdigit():
            total += int(token)
            found = True
    return total if found else None


def _rocm_vram() -> int | None:
    text = _run(["rocm-smi", "--showmeminfo", "vram"])
    # rocm-smi prints "VRAM Total Memory (B): 1234" on current releases.
    total = 0
    found = False
    for line in text.splitlines():
        if "vram" not in line.lower() or "total" not in line.lower():
            continue
        digits = "".join(ch if ch.isdigit() else " " for ch in line).split()
        if not digits:
            continue
        raw = int(digits[-1])
        total += raw // (1024 * 1024) if raw > 1024 * 1024 else raw
        found = True
    return total if found else None


def _apple_vram_note() -> str:
    if platform.system() != "Darwin":
        return ""
    if shutil.which("powermetrics") is None:
        return "powermetrics not installed; Apple Silicon VRAM reported as shared RAM"
    # powermetrics needs root and is slow. Absence-or-unprivileged is a note,
    # not a crash. We do not invoke it.
    return "powermetrics present but not queried (requires privileges)"


def collect_telemetry(*, tokens_per_sec: float | None = None) -> HardwareTelemetry:
    """Best-effort RAM, VRAM, and an optional tokens/sec sample.

    ``tokens_per_sec`` is supplied by the caller that just timed a generation.
    This function never measures a model itself and never raises.
    """
    try:
        ram_total, ram_free = _ram()
        vram = _nvidia_vram()
        source = "nvidia-smi" if vram is not None else ""
        if vram is None:
            vram = _rocm_vram()
            source = "rocm-smi" if vram is not None else ""
        notes = []
        apple = _apple_vram_note()
        if apple:
            notes.append(apple)
        if vram is None:
            source = "unavailable"
            notes.append("no NVIDIA/AMD telemetry tool responded")
        rate = None
        if tokens_per_sec is not None:
            try:
                rate = float(tokens_per_sec)
            except (TypeError, ValueError):
                rate = None
            if rate is not None and rate < 0:
                rate = None
        if rate is None:
            notes.append("tokens/sec not sampled this call")
        return HardwareTelemetry(
            ram_total_mb=ram_total,
            ram_available_mb=ram_free,
            vram_total_mb=vram,
            vram_source=source or "unavailable",
            tokens_per_sec=rate,
            note="; ".join(notes),
        )
    except Exception as exc:  # noqa: BLE001 — the whole point of this probe
        return HardwareTelemetry(
            ram_total_mb=None,
            ram_available_mb=None,
            vram_total_mb=None,
            vram_source="unavailable",
            tokens_per_sec=None,
            note=f"telemetry failed: {type(exc).__name__}",
        )
