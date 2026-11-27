#!/usr/bin/env python3
"""Time the stages of a voice turn.

This does not open a microphone. On the Ubuntu workstation, run a real
Pipeline turn with the app, then pass the stage durations you measured:

    python scripts/voice_benchmark.py --ptt-ms 40 --stt-ms 180 --ttft-ms 420 --tts-ms 260

With no numbers, it prints the command and the config keys that change
echo behavior. Exit 0 either way.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report a voice-turn timing.")
    parser.add_argument("--ptt-ms", type=float, default=None)
    parser.add_argument("--stt-ms", type=float, default=None)
    parser.add_argument("--ttft-ms", type=float, default=None)
    parser.add_argument("--tts-ms", type=float, default=None)
    args = parser.parse_args(argv)
    stages = {
        "ptt": args.ptt_ms,
        "stt": args.stt_ms,
        "ttft": args.ttft_ms,
        "tts": args.tts_ms,
    }
    if all(value is None for value in stages.values()):
        print("No stage timings were passed.")
        print("On the Ubuntu host, time one push-to-talk turn and rerun:")
        print(
            "  python scripts/voice_benchmark.py "
            "--ptt-ms <n> --stt-ms <n> --ttft-ms <n> --tts-ms <n>"
        )
        print("Half-duplex mic mute is [audio].half_duplex in jarvis.toml.")
        print("A loud barge-in while that mute is on uses [audio].barge_in_energy.")
        return 0
    total = sum(value for value in stages.values() if value is not None)
    for name, value in stages.items():
        if value is not None:
            print(f"{name}: {value:.0f} ms")
    print(f"sum: {total:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
