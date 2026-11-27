# Good Boy 1.1.0 — Code Review and Remediation Report

Date: 2026-11-27. Scope: the Good Boy tree after the 1.1.0 hardening pass.

This is not a line-by-line reading of every file in an 11,000-file tree. The review read the execution paths named in the audit: the event bus, local-provider routing, tool-call repair, mission critic and worktree cleanup, archive extraction, bind policy, the injection scanner, the Ollama install/start path, and the tests that claim to cover those guards. Citations are `file:line` from that reading.

## Executive verdict

**Needs Hardening.**

Not blocking for a local desktop session. The Linux install script is now checksum-pinned. Still open: the Windows Ollama exe is unhashed, typed bus handlers can stall a publisher, and the display name does not match the frozen install identity.

Strengths that held up under reading:

- Subprocess launches in the mission and admin paths are argument vectors. A search for `shell=True` in `jarvis/` hits comments that forbid it, not call sites that set it.
- Skill and wiki uploads canonicalize paths and refuse `..` before write (`jarvis/core/uploads.py:131`, `jarvis/core/uploads.py:297`).
- Typed event-bus errors are logged inside `_safe_dispatch` and do not escape `publish` (`jarvis/core/bus.py:101`).
- A local active brain is stripped of paid hops unless the user opts in (`jarvis/brain/manager.py:10781`).
- Listeners default to loopback, and a non-loopback bind now needs both `JARVIS_BIND_HOST` and a control key (`jarvis/ui/web/control_auth.py:70`).

Top risks:

- The Linux Ollama script is now pinned. The Windows `OllamaSetup.exe` download is still executed without a checksum.
- Typed EventBus handlers have no timeout. One slow subscriber stalls every publisher (`jarvis/core/bus.py`). That cap stays off because playback handlers await audio, and a regression test requires it.
- The display name and the frozen install identity still disagree (CR-11).

## Findings

### HIGH — Unpinned remote script is executed to install Ollama

- **ID:** CR-01
- **Location:** `jarvis/brain/ollama_runtime.py` (`_LINUX_INSTALL_SCRIPT_SHA256`, `_install_linux`)
- **Category:** Security
- **Issue:** `_install_linux` downloads `https://ollama.com/install.sh` and runs it with `sh` when passwordless sudo is available. `_setup_local_brain` calls `ensure_runtime_blocking()`, which takes that path when the binary is missing. The bytes were not hashed. A change on that host becomes code execution during “set up local models.” Chat failover does not call this. The local-model install does.
- **Fix:** Applied. The script is hashed after download and deleted when the digest does not match the pin reviewed on 2026-11-27. The Windows `OllamaSetup.exe` download is still unpinned.

### HIGH — Wake-model zip could write outside the temp dir

- **ID:** CR-02
- **Location:** `jarvis/speech/wake_model_fetch.py:147` (was an unfiltered `extractall` at the old call)
- **Category:** Security
- **Issue:** The Vosk zip was unpacked with `ZipFile.extractall` and no member check. A member named `../` writes beside the temp directory. Current language zips are SHA-256 pinned, so a swapped zip fails the hash. The extractor itself did not confine paths, and the module docstring still allows an empty hash to be accepted unverified.
- **Fix:** Applied. `_extract_zip_safely` rejects `..` and absolute members, then extracts with `filter="data"` where that argument exists.

### HIGH — Injection rule killed ordinary documentation

- **ID:** CR-03
- **Location:** `jarvis/missions/safety/injection_scanner.py:130`, kill site `jarvis/missions/kontrollierer/orchestrator.py:2560`
- **Category:** Security
- **Issue:** The first 1.1.0 pattern treated `read` within 80 characters of `api keys` as critical. `has_high_severity` then emits `WorkerKilled(injection_detected)`. A worker that quoted “read the API keys section” would be killed before review. The scanner’s own history says this class of pattern already killed live missions.
- **Fix:** Applied. The pattern now requires an exfil verb (`export`, `cat`, `print`, `send`, `upload`, `exfiltrate`) and a secret path (`~/.ssh`, `id_rsa`, `id_ed25519`). “Ignore previous instructions” is still high via the older `ignore_previous` rule.

### HIGH — Last tool-repair attempt discarded a valid call

- **ID:** CR-04
- **Location:** `jarvis/reliability/tool_repair.py:129`
- **Category:** Local AI
- **Issue:** `plan_tool_repair` used to escalate as soon as `attempt >= 2`, before parsing. The model’s successful third payload was thrown away and the person was told the action failed.
- **Fix:** Applied. A usable call is returned at any attempt. Escalation happens only when that attempt is still not a call.

### MEDIUM — Typed bus handlers can stall the process

- **ID:** CR-05
- **Location:** `jarvis/core/bus.py:37`, `jarvis/core/bus.py:91`, `jarvis/core/bus.py:105`
- **Category:** Concurrency
- **Issue:** Wildcard observers time out after 5 seconds. Typed subscribers are awaited with no cap, on purpose, because some of them play audio. A typed handler that blocks (a lock, a synchronous HTTP call, a stuck playback await) stalls `publish` for every other layer. `subscribe` / `unsubscribe` also mutate the handler list without the lock `publish` does not hold either. CPython’s GIL makes the list snapshot usually safe. A free-threaded build can tear it.
- **Fix:** Typed handlers stay uncapped. `tests/unit/core/test_bus_wildcard_timeout.py` requires a slow typed subscriber to finish, because playback awaits audio. The list mutation is now under a `threading.Lock` shared with the publish snapshot (CR-13).

### MEDIUM — Critic ping-pong is capped, but the new breaker does not see it

- **ID:** CR-06
- **Location:** `jarvis/missions/critic/runner.py:588`, `jarvis/missions/kontrollierer/orchestrator.py:1620`, `jarvis/missions/kontrollierer/orchestrator.py:1966`
- **Category:** Concurrency
- **Issue:** Architect/developer revise loops stop at `MAX_CRITIC_LOOPS` (3). They cannot ping-pong forever. The 1.1.0 `FailureCircuit` only wraps the timeout / transient / auth retry branch. Two different critic objections still consume the full three iterations. That is a cap, not a “same mistake” breaker.
- **Fix:** Applied. A second identical `correction_instruction` returns `EXHAUSTED` and logs the crew escalation. A different objection still consumes the three-iteration cap.

### MEDIUM — Sandbox delete could target the outputs root

- **ID:** CR-07
- **Location:** `jarvis/missions/isolation/worktree.py:493`
- **Category:** Security
- **Issue:** `path_is_inside` is true when the candidate is the sandbox root. `WorktreeManager.remove` would then try to delete the whole mission-output tree.
- **Fix:** Applied. Removal is refused when the path resolves to the outputs root or to anything outside it.

### MEDIUM — Sherpa archive fallback still trusts links on old Python

- **ID:** CR-08
- **Location:** `jarvis/speech/sherpa_models.py:76`
- **Category:** Security
- **Issue:** `tarfile.extractall(..., filter="data")` is correct on current Python. The `TypeError` fallback used to extract with no filter. Parent-segment names are now rejected before that fallback. A symlink member whose name is innocent can still point outside the tree on a Python that lacks `filter`.
- **Fix:** Applied for the fallback. Parent paths, symlinks, hard links, and anything that is not a regular file or directory are rejected before the unfiltered `extractall`. Current Python still uses `filter="data"`.

### MEDIUM — Context compaction can put the prompt back over the budget

- **ID:** CR-09
- **Location:** `jarvis/reliability/context_pressure.py` (scratchpad insert after the drop loop)
- **Category:** Local AI
- **Issue:** Protected system and security-rule messages are not evicted. After the drop loop, a scratchpad note is inserted and is not measured again. On a very small window that note can push the estimate back over 85%. Security text is not summarized away.
- **Fix:** Applied. A note that does not fit is replaced by a one-line marker. If that marker still does not fit, it is omitted.

### MEDIUM — Speaker-echo transcript filter is not on the hot path

- **ID:** CR-10
- **Location:** `jarvis/reliability/acoustic.py` (`phantom_transcript`); wake bar in `jarvis/plugins/wake/openwakeword_provider.py`
- **Category:** Local AI
- **Issue:** While speakers are active the wake score bar rises by 0.15. That part is wired. `phantom_transcript` correctly classifies “the mic heard the line TTS just spoke,” and a unit test covers it. Nothing in the speech pipeline calls it, so a phantom transcript can still become a turn.
- **Fix:** Not applied, and not needed as a second filter. `_looks_like_self_echo` already drops speaker echo on the final-transcript path (`jarvis/speech/pipeline.py`, `SelfEchoGuard`). `phantom_transcript` would also drop a short genuine answer that reuses the assistant's words (the case `test_user_answer_with_novel_word_is_kept` keeps). The wake score bar remains the acoustic half.

### MEDIUM — Brand and installer identity are split

- **ID:** CR-11
- **Location:** `jarvis/core/branding.py:14`, `jarvis/core/branding.py:59`, `README.md`, `install/install.sh`
- **Category:** Packaging
- **Issue:** The README title, installer welcome, and CLI startup lines say Good Boy. `PRODUCT_NAME` is still `Personal Jarvis`. The official repo slug is still `PersonalJarvis/PersonalJarvis`. A frozen identity test refuses to change those strings because they are install paths, keyring names, and bundle ids. A clean `install.sh` clones the upstream slug, not `tbwcheatwood-hue/Good-Boy`, unless `JARVIS_OFFICIAL_REPO_SLUG` is set. Historical docs still say Hue and Personal Jarvis. That is not “only license files.”
- **Fix:** Either migrate the display name through `branding.py` and the freeze test together, or document the split in the installer banner so a new user is not surprised. Not applied; changing the slug without a migration orphans updates.

### LOW — Secret redaction marker is not `***`

- **ID:** CR-12
- **Location:** `jarvis/core/redact.py:93`
- **Category:** Security
- **Issue:** Keys are masked as `<redacted:name>`, not three asterisks. The mask is applied on decision-log previews. Changing the token would break every test that pins the current marker.
- **Fix:** Leave the marker. It is a mask, and it keeps the secret type visible to a person reading a log.

### LOW — Subscription list mutation is unsynchronized

- **ID:** CR-13
- **Location:** `jarvis/core/bus.py:53`
- **Category:** Concurrency
- **Issue:** Called out separately because a reconnect that forgets `unsubscribe_all` leaks a wildcard handler. The API to detach exists. Call sites still have to use it.
- **Fix:** Applied for the race. `subscribe`, `unsubscribe`, and the publish snapshot share `threading.Lock`. Forgetting `unsubscribe_all` is still a caller bug.

## Stub and honesty matrix

| Advertised surface | Status | What the code actually does |
| --- | --- | --- |
| Local endpoints (Ollama, LM Studio, llama.cpp) | Partial | Routing refuses a silent hop to a paid provider. The app can still install and start Ollama when a local-model setup runs (CR-01). It does not kill an Ollama it did not start (`ollama_runtime.py` stop path). |
| Tool-call repair for small models | Verified, with the CR-04 fix | Markdown JSON, trailing commas, and a few parameter aliases are repaired. Two failed repairs escalate. A valid last attempt is kept. |
| Context compaction | Partial | Security-role and security-phrase messages stay. The scratchpad can overshoot a tiny window (CR-09). |
| The Crew / critic loop | Partial | Hard stop at 3 critic iterations. Identical timeout/auth failures escalate on the second hit. Identical revise text does not (CR-06). |
| CLI coding agents | Verified at the spawn boundary | Workers go through `create_subprocess_exec`-style helpers. No `shell=True` call site in `jarvis/`. Missing binaries surface as worker errors rather than a shell. |
| Git worktrees | Verified after CR-07 | `remove` refuses the outputs root and any path that resolves outside it. |
| Voice / wake vs speakers | Partial | Wake threshold rises during playback. Phantom-transcript drop is tested and not wired (CR-10). Realtime barge-in still uses the envelope correlator. |
| MCP / untrusted tool output | Partial | Tool text that matches the injection phrases is labeled data, and a later secret-path call is blocked unless the person’s own words asked for it. Not every web fetch is wrapped. |
| HTTP bind | Verified | Default `127.0.0.1`. Non-loopback requires `JARVIS_BIND_HOST` equal to that host plus a control key. |
| Installers | Partial | Welcome copy says Good Boy. Clone URL still follows the frozen upstream slug (CR-11). Missing Python/git already produce an actionable message. |
| Secret scrubbing | Verified, different mask | `redact_secrets` masks credential shapes. The token is `<redacted:…>` (CR-12). |

## Applied patches and verification

Applied in the working tree, after the `Good-Boy-v1.1.0.zip` archive was built. That zip does not contain these review fixes. They are not on GitHub.

| ID | Change |
| --- | --- |
| CR-02 | `jarvis/speech/wake_model_fetch.py`: `_extract_zip_safely` |
| CR-03 | `jarvis/missions/safety/injection_scanner.py`: narrower `ssh_or_key_exfil` |
| CR-04 | `jarvis/reliability/tool_repair.py`: parse before escalate |
| CR-07 | `jarvis/missions/isolation/worktree.py`: refuse deleting the outputs root |
| CR-08 | `jarvis/speech/sherpa_models.py`: reject `..` members before the unfiltered tar fallback |

Not applied, with reason: CR-05 (typed handlers are intentionally uncapped; playback), CR-10 (`SelfEchoGuard` already covers the hot path, and the extra classifier would drop a real short answer), CR-11 (frozen install identity), CR-12 (the mask is already a mask). The Windows Ollama exe download is still unhashed.

Command that passed after the patches:

```text
.venv/bin/python -m pytest tests/unit/reliability/test_phase2_guards.py tests/missions/test_injection_scanner.py tests/missions/test_worktree.py -q --tb=short
```

Result: 86 passed. The new cases cover a valid tool call on attempt 2, “read the API keys section” not killing a scan, `cat ~/.ssh/id_rsa` still matching, and a zip member `../outside.txt` raising `ValueError` without writing the file.

What this run did not do: a live local model, a microphone latency measurement, a Windows or macOS install, or a full `CI gate`.
