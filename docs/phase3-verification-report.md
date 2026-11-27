# Good Boy 1.2.0 — verification report

Date: 2026-11-27. Release archive: `Good-Boy-v1.2.0.zip`. The SHA-256 is the sibling file `Good-Boy-v1.2.0.zip.sha256`.

`unzip -t` reported no errors. The archive does not contain `.venv`.

The release number is 1.2.0. `ENGINE_LINEAGE` is 3.1.1, the upstream engine this tree was cut from. Install paths, the keyring service, and `jarvis.toml` are unchanged so an existing data directory is not orphaned. The Python distribution name stays `personal-jarvis` because extras and install probes address it by that name. The clone target and the in-app repository links are `https://github.com/tbwcheatwood-hue/Good-Boy`.

## What was fixed

### 1. SOUL and filelock

`filelock` was already declared in `pyproject.toml` (base dependencies) and pinned in `requirements.txt`. The three SOUL tool tests had failed in a virtualenv that never installed that dependency; `edit_soul` imports `filelock` at call time. A base install from `requirements.txt` now has it, and those tests pass here.

A first-run workspace still calls `render_soul_md()` and does not overwrite an existing `SOUL.md`. The template, and the `SOUL.md` shipped in the tree, now seed Sam: name, loyal grounded urban-industrial tone, limits, and an empty Calibration block the person can edit.

### 2. Repository, version, packaging

`jarvis --version` prints `Good Boy 1.2.0 (engine 3.1.1)`. `DEFAULT_OFFICIAL_REPO_SLUG` and the four installer projections (`install.sh`, `install.ps1`, `install-verify.sh`, `install-verify.ps1`) point at `tbwcheatwood-hue/Good-Boy`. README, the headless guide, and the product install guide use that clone URL. The desktop shortcut filename stays `personal-jarvis.desktop` because that name is the frozen install identity.

### 3. Port

The process listens on `127.0.0.1:47821` (`[ui].admin_api_port` in `jarvis/core/config.py`). README had said 8442. README, the configuration reference, the headless guide, and the local-AI guide now say 47821 for Good Boy and leave 11434, 8080, and 1234 as the model servers. Override the app port with `[ui].admin_api_port`. A non-loopback bind still needs `JARVIS_BIND_HOST` and a control key.

Local AI, audio, and wiki product docs were checked against the code. Ollama, an OpenAI-compatible llama.cpp or LM Studio server, Whisper, Nemotron, and Piper match the provider cards. The wiki guide does not name a listen port.

### 4. Event bus

`publish` waits at most 0.15 seconds. Handlers still running are left on the loop. Wildcard handlers still hit their own timeout. Typed handlers are not cancelled, so playback can finish after the publisher has moved on. A test subscribes one handler that sleeps 2 seconds and one that records the event: publish returns in under half a second and the healthy handler has run.

### 5. Tokens and compaction

`estimate_tokens` uses tiktoken `cl100k_base` with a 15% margin when that package is installed. Otherwise it uses 3 characters per token, which over-counts English and stays inside a small window. Compaction drops an assistant tool call together with the tool results that follow it. System and security-rule messages stay. Tests cover 4k, 8k, and 32k windows.

tiktoken is optional. It is not required for a headless boot.

### 6. Echo

`[audio].half_duplex` drops microphone frames while `playback_active()` is true. `[audio].barge_in_energy` keeps a frame at least that loud, for a headset or hardware echo cancellation. The existing `SelfEchoGuard` still drops a transcript that is only words just spoken. `scripts/voice_benchmark.py` sums stage timings you pass in. It does not open a microphone.

### 7. Artifacts and the live harness

Python deliverables are syntax-checked and then executed from a copy in a temporary directory, with a 5 second timeout, a stripped environment, and a socket hook. `unshare --net` is used when it works. JavaScript runs under `node` when `node` is installed. Shell scripts run under `bash` or `sh` the same way. JSON is still parsed and not executed.

`scripts/live_local_smoke.py` probes Ollama on 11434, then an OpenAI-compatible server on 8080, then LM Studio on 1234. It exits 0 when nothing is listening. `pytest -m live_local` stays skipped unless `GOOD_BOY_LIVE_LOCAL=1`.

## What ran

```text
.venv/bin/python -m pytest \
  tests/unit/plugins/tool/test_update_soul.py \
  tests/unit/memory/test_soul.py \
  tests/unit/memory/learning/test_soul_learning.py \
  tests/unit/reliability/test_phase2_guards.py \
  tests/unit/core/test_bus_wildcard_timeout.py \
  tests/unit/core/test_bus_unsubscribe_all.py \
  tests/missions/test_event_bus.py \
  tests/unit/core/test_branding.py \
  tests/unit/install/test_branding_contract.py \
  tests/unit/ui/web/test_update_routes.py \
  tests/unit/ui/test_socials_routes.py \
  tests/unit/ui/web/test_feedback_routes.py \
  tests/live/test_local_model_smoke.py \
  -q --tb=line
```

Result: 143 passed, 1 skipped, 0 failed. The skip is the live-local test, because `GOOD_BOY_LIVE_LOCAL` was not set. `scripts/live_local_smoke.py` printed that no local server was running and exited 0. `scripts/voice_benchmark.py` printed the Ubuntu command and, with sample numbers, a 900 ms sum.

The speech-pipeline self-echo module tests were not collected here: importing the pipeline needs `numpy`, which is not installed in this virtualenv. Those tests already cover `SelfEchoGuard` and were not edited.

The full tree was not executed. This virtualenv does not have the optional native stack the whole suite imports. The command above is the set that covers the seven fixes, including the SOUL tests that previously failed on `filelock`.

## Run the live checks on Ubuntu

Local model, one real completion, only if a server is already up:

```bash
python scripts/live_local_smoke.py
GOOD_BOY_LIVE_LOCAL=1 pytest -m live_local -q
```

Voice timings, after you measure one push-to-talk turn on that machine:

```bash
python scripts/voice_benchmark.py --ptt-ms <n> --stt-ms <n> --ttft-ms <n> --tts-ms <n>
```

Half-duplex for a speaker the microphone can hear:

```toml
[audio]
half_duplex = true
barge_in_energy = 0.2
```

`barge_in_energy = 0` keeps the microphone closed for the whole playback.
