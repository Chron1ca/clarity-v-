# Clarity.V v1.0 Build Plan

**Standing rule:** Completion is the only metric. A phase is done when its verification command ran and produced the expected output. Not when the code looks right. Not when "it should work." When the verification confirmed it.

If verification fails, the phase isn't done. The next phase doesn't start.

No claiming what wasn't proven. Every reported "done" links to the verification output that proved it.

**Self-verification pauses are mandatory, not optional.** After every module written, run its unit tests. After every architectural change touching multiple files, run the full test suite. After every dependency change, smoke-test that the touched modules still import. These pauses aren't slowing you down — they catch the regressions that take 10x longer to find later.

A phase whose code is written but whose verification is pending is **not complete**. It is "implementation done, verification pending." That's a fine state to surface; claiming "done" without the verification step is the failure mode the standing rule exists to prevent.

---

## Phase 0 — Verify what's already on disk

Before writing more code, prove what's there is correct.

### 0.1 — Project doc + scaffold parse

**Action:** none (already done).

**Verify:**

```bash
# JSON files parse
python -c "import json; json.load(open('dictionaries/default.json'))"
python -c "import json; json.load(open('dictionaries/python.json'))"

# Python stubs parse
python -c "import ast; ast.parse(open('src/clarity_v/__init__.py').read())"
python -c "import ast; ast.parse(open('src/clarity_v/platform/__init__.py').read())"
python -c "import ast; ast.parse(open('src/clarity_v/platform/_base.py').read())"
python -c "import ast; ast.parse(open('src/clarity_v/platform/windows.py').read())"
python -c "import ast; ast.parse(open('run.pyw').read())"
```

**Expected:** all six commands exit 0 with no output. Any JSONDecodeError or SyntaxError = failure.

### 0.2 — Upstream prototype: repeat-filter behavior

The repeat-filter algorithm was prototyped upstream before being ported here. Verifying the algorithm separately gives confidence in the port.

**Verify (against the in-repo implementation):**

```bash
python -c "
import sys; sys.path.insert(0, 'src')
from clarity_v.filters import strip_repeated_sentences
assert strip_repeated_sentences('Hello. Hello. Hello.') == 'Hello.'
assert strip_repeated_sentences('First. Second. First.') == 'First. Second.'
print('repeat filter OK')
"
```

**Expected:** `repeat filter OK`. Anything else = failure.

---

## Phase 1 — Pure-function spine

The pieces that need no microphone, no model load, no real OS interaction. Easiest to verify deterministically.

### 1.1 — `src/clarity_v/filters.py`

**Build:**

- `strip_repeated_sentences(text)` — Whisper's silence-loop dedupe
- `strip_known_hallucinations(text)` — port HALLUCINATIONS list + match logic
- `strip_wake_phrase(text, phrases)` — port the regex-strip
- Module-level `HALLUCINATIONS` constant (with PT additions: "obrigado por ver", etc.)

**Verify:**

```bash
python -m pytest tests/test_filters.py -v
```

Test cases that must pass:

- `strip_repeated_sentences("A. A. A.")` → `"A."`
- `strip_repeated_sentences("A. B. A.")` → `"A. B."`
- `strip_repeated_sentences("")` → `""`
- `strip_known_hallucinations("Thank you for watching.")` → `""`
- `strip_known_hallucinations("Real text. Thank you.")` → `"Real text."` (trailing strip)
- `strip_wake_phrase("clarity-v start a recording", ["clarity-v"])` → `"start a recording"`

**Expected:** all tests pass, pytest exits 0.

### 1.2 — `src/clarity_v/dictionary.py`

**Build:**

- `Dictionary` class
- `Dictionary.load(path)` — loads JSON, resolves `extends:` chain (default ← python)
- `Dictionary.apply_substitutions(text)` — case-insensitive phrase replacement
- `Dictionary.expand_macros(text)` — finds macro triggers, replaces with template
- `Dictionary.match_voice_command(text, phase)` — returns command dict or None
- Hot-reload via file watcher (background thread) — verifies later

**Verify:**

```bash
python -m pytest tests/test_dictionary.py -v
```

Test cases:

- `Dictionary.load("dictionaries/default.json")` → has expected substitutions
- `Dictionary.load("dictionaries/python.json")` → has python.json substitutions PLUS inherited default.json substitutions
- `dict.apply_substitutions("git hub is cool")` → `"GitHub is cool"` (case-insensitive)
- `dict.expand_macros("deffunc here")` → `"def function_name(args):\n    pass here"`
- `dict.match_voice_command("send", "after")` → `{"action": "submit"}`
- `dict.match_voice_command("send", "during")` → `None` (wrong phase)
- Reload after editing file picks up new entries

**Expected:** all tests pass.

### 1.3 — `src/clarity_v/state.py`

**Build:**

- `State` enum: IDLE, RECORDING, PROCESSING, COMMIT_WAITING, ERROR
- `StateManager` — broadcasts state changes to subscribers
- `StateManager.subscribe(callback)` — for the glow bar to listen
- `StateManager.set_state(state, info=None)` — atomic state change
- No threading lock issues — verifiable via concurrent test

**Verify:**

```bash
python -m pytest tests/test_state.py -v
```

Test: spin up StateManager, register 3 subscribers, fire 100 state changes from a thread, assert all 3 subscribers received all 100 in order.

**Expected:** all tests pass.

---

## Phase 2 — Whisper engine

First piece that needs a real model load. Verifies STT works locally.

### 2.1 — `src/clarity_v/whisper_engine.py`

**Build:**

- `WhisperEngine(model_size="medium", device="auto")` — loads faster-whisper
- `WhisperEngine.transcribe(audio_float32, language=None, beam_size=5, initial_prompt=...)` → (text, detected_language)
- Pipeline:
  1. Whisper raw transcribe (language=None)
  2. Apply `strip_repeated_sentences`
  3. Apply `strip_known_hallucinations`
  4. Optional: apply wake-phrase strip if wake_phrases provided
- Returns `(cleaned_text, detected_language, raw_text)` so the caller can log the filter chain

**Verify:**

```bash
# Record two test WAVs (one PT, one EN) once, commit to tests/fixtures/
python tools/record_test_wavs.py  # one-time setup

# Then on every verification:
python tools/verify_whisper.py
```

`tools/verify_whisper.py` script does:

```python
from clarity_v.whisper_engine import WhisperEngine
engine = WhisperEngine()

# English
text, lang, raw = engine.transcribe_file("tests/fixtures/sample_en.wav")
assert lang == "en", f"Expected en, got {lang}"
assert len(text) > 5, f"Empty transcription"
print(f"[EN] lang={lang} text={text!r}")

# Portuguese
text, lang, raw = engine.transcribe_file("tests/fixtures/sample_pt.wav")
assert lang == "pt", f"Expected pt, got {lang}"
assert len(text) > 5, f"Empty transcription"
print(f"[PT] lang={lang} text={text!r}")
```

**Expected:** both pass. Language detection correctly identifies each. Text is non-empty. If PT doesn't detect as `pt`, the language-pin work isn't done.

---

## Phase 3 — Audio capture

Verifies microphone input works.

### 3.1 — `src/clarity_v/audio.py`

**Build:**

- `AudioCapture(sample_rate=16000, blocksize=4000)`
- `.start(callback)` — sounddevice InputStream with the callback
- `.stop()`
- `.list_devices()` — for mic selector
- Buffer management: chunks list, `concat()` method, `clear()`

**Verify:**

```bash
python tools/verify_audio.py
```

Script that:

1. Lists devices, prints them.
2. Captures 3 seconds of audio with default device.
3. Asserts buffer length matches expected sample count.
4. Asserts buffer is not all zeros (mic actually picked up audio — prompts the Person to say something).
5. Saves to `tests/fixtures/last_capture.wav` for inspection.

**Expected:** runs without exceptions, buffer has non-zero data, WAV file is playable.

---

## Phase 4 — Wake detection

Verifies wake-word system works in isolation.

### 4.1 — `src/clarity_v/wake.py`

**Build:**

- `WakeDetector(config_path)` — loads OpenWakeWord models
- `.feed(chunk)` → optional WakeEvent (`{"model": "clarity-v", "score": 0.87, "chunk_idx": N}`)
- Multiple models support (clarity-v + stop = two separate models)
- Cooldown enforcement (drop detections within `cooldown_seconds` of last)
- Reset method (clears internal state — used after detection)

**Verify:**

```bash
python tools/verify_wake.py
```

Script that:

1. Loads default config (the `cv_go` start-dictation wake — ONNX model loaded from the configured path).
2. Captures 10 seconds of audio with mic.
3. Prompts: "Say 'see vee go' once."
4. Feeds chunks to detector, prints scores.
5. Asserts at least one detection event fired with score > threshold.
6. Asserts cooldown works: artificially feed a high-score chunk twice in quick succession, only one event fires.

**Expected:** detection event fires when "see vee go" said. Cooldown enforced.

---

## Phase 4.5 — Custom wake-word training pipeline

The pre-trained `hey_jarvis` is fine for first-run testing. For v1.0 ship, the goal is a custom wake word trained heavy on synthetic + personal-voice samples. This phase is the *pipeline*; the actual training run is a separate (multi-hour) execution the user kicks off.

### 4.5.1 — `tools/training/generate_samples.py`

**Build:** parametric sample generator (any wake phrase via `--phrase` + `--model-name`), Edge TTS, 50+ voices across 14 English accents + PT/ES/FR/DE/IT for robustness, multiple phrasings, rate & pitch variations, ~5000 samples per run with resume support. Writes 80/20 into `positive_train/` + `positive_test/`.

**Verify:**

```bash
python tools/training/generate_samples.py --phrase "test phrase" --model-name test_phrase --target 50
ls models/training_data/my_custom_model/test_phrase/positive_train/*.wav | wc -l   # expect ~40
ls models/training_data/my_custom_model/test_phrase/positive_test/*.wav | wc -l    # expect ~10
```

### 4.5.2 — `tools/training/record_personal_voice.py`

**Build:** records the Person saying the phrase 25 times with countdown, auto-trims silence, applies 20 augmentations per take (pitch shift ±200 cents, time stretch 0.92-1.08x, light noise) → ~500 personal samples per session. Same 80/20 layout as 4.5.1.

**Verify:** runs interactively; check `models/training_data/my_custom_model/<model-name>/positive_train/personal_*.wav` + `positive_test/personal_*.wav` count matches `takes × (1 + augments-per-take)`.

### 4.5.3 — `tools/training/fetch_negatives.py`

**Build:** downloads everything `train.py` reads from disk: piper-sample-generator + openwakeword repos, ACAV100M + validation feature `.npy` files, MIT room-impulse-response set, Piper voice checkpoint. Idempotent — re-runs skip what's already on disk. Total ~17.5 GB on a cold cache.

**Verify:** `models/training_data/` contains `piper-sample-generator/`, `openwakeword/`, `mit_rirs/`, `openwakeword_features_ACAV100M_2000_hrs_16bit.npy`, `validation_set_features.npy` after a complete run.

### 4.5.4 — `tools/training/train.py`

**Build:** wraps OpenWakeWord's training API. Logs clear errors if the upstream API signature shifts (it has, between versions). Pinned versions live in `tools/training/requirements.txt`. Skip-existing-stage logic so re-runs don't redo the hours-long generate stage; Windows CUDA/ONNX cleanup-crash exit code treated as success.

**Verify:** training run completes, ONNX file exists at `models/wake_words/<model-name>.onnx`.

### 4.5.5 — `tools/training/validate.py`

**Build:** two-stage interactive validation — detection rate test (10 takes, must hit 8+/10) and false-positive test (30 s of normal speech, must hit ≤1). If both pass, offers to deploy: copies the ONNX into `models/wake_words/` and updates `wake_config.json`.

**Verify:** Person speaks the phrase 10 times, talks normally for 30 s, validation script reports the metrics and (on pass) deploys.

### 4.5.6 — `wake.py` custom-path support

**Build:** WakeDetector accepts model entries with `model_path: "..."` pointing to a custom ONNX file. Missing files log clearly and fall back to OpenWakeWord pre-trained `hey_jarvis` so the engine never hard-fails on a missing model.

**Verify:**

```bash
python -c "
import sys; sys.path.insert(0, 'src')
from clarity_v.wake import WakeDetector
d = WakeDetector({'models': [{'name': 'x', 'model_path': 'nonexistent.onnx', 'threshold': 0.5}]})
assert d.enabled, 'fallback failed'
print('fallback OK')
"
```

**Documentation:** `TRAINING.md` at repo root explains the full pipeline AI-readably for an AI agent helping a Person through the training process. `models/wake_words/README.md` explains the deployment directory.

---

## Phase 5 — Dictation orchestrator

The state machine. All pieces wired.

### 5.1 — `src/clarity_v/dictation.py`

**Build:**

- `DictationEngine` — composes WakeDetector, AudioCapture, WhisperEngine, Dictionary, StateManager
- State machine: IDLE → RECORDING → PROCESSING → COMMIT_WAITING → IDLE
- Wake handler: on wake event, transition IDLE→RECORDING
- Stop handler: **explicit Person signals only by default** — `cv_over` stop wake or the stop keybind. Silence-detection and wake-refire exist as opt-in alternatives (Person sets `silence_seconds_to_stop > 0` in Settings). The AI does not autonomously decide when the recording ends. On any Person-initiated stop signal, transition RECORDING→PROCESSING.
- Process: transcribe with Whisper, run filter chain, apply dictionary, paste via platform adapter
- Cleanup discipline: every short-circuit (empty / too short / hallucination) returns to IDLE explicitly

**Verify:**

End-to-end script `tools/verify_dictation.py`:

1. Open Notepad.
2. Start DictationEngine.
3. Script prompts: "Say 'see vee go', then 'hello world this is a test', then 'see vee over'."
4. Wait up to 20 seconds.
5. Read Notepad's content via clipboard or accessibility API.
6. Assert content contains "hello world".

**Expected:** Notepad contains the transcribed message. State returned to IDLE after.

This is the first phase that proves the WHOLE thing works.

---

## Phase 6 — Voice-commit listener (post-paste Whisper window)

**Architectural clarification (corrected 2026-05-22):** The wake detector
(OpenWakeWord) only fires on pre-trained phrases. "enter" / "send" / "new
paragraph" are NOT wake-word phrases — they're detected by running
**Whisper** on the post-paste audio window and string-matching the
transcript against the voice_commands map. Pattern: short fixed-duration
post-paste window, single Whisper transcribe at the end, beam_size=1 for
speed (action transcripts are short).

### 6.1 — `src/clarity_v/commit.py`

**Build:**

- After paste, transition state to COMMIT_WAITING.
- Continue capturing audio for N seconds (default 5; configurable).
- After the window closes, transcribe the captured buffer with Whisper
  (beam_size=1 for speed; the buffer is short).
- Apply filter chain (the captured audio is mostly silence — likely to
  hallucinate; the repeat-filter + known-phrase filter must run).
- Pass the cleaned transcript to `Dictionary.match_voice_command(text, phase="after")`.
- If match: call `platform.send_key_combo(combo)` from the command's action.
- If no match OR timeout: return to IDLE.

**Stop detection (separate from commit):** the "stop" voice command that
ends the main recording can be handled three ways:
  (a) Wake word re-fire (say "clarity-v" again to stop)
  (b) Silence detection — recording auto-ends after N seconds of
      sub-threshold audio (OPT-IN; default OFF — the Person, not the
      AI, decides when their message ends)
  (c) Custom-trained "stop" OpenWakeWord model (future)

**Verify:**

`tools/verify_commit.py`:

1. Open Notepad (or any app where Ctrl+Enter is meaningful).
2. Run engine, prompt: "Say 'see vee go', 'hello world', wait for paste, then say 'send' within 5 seconds."
3. Assert text appeared AND Ctrl+Enter was synthesized (Notepad inserts newline).

**Expected:** text + line break visible. Confirms voice-commit fires.

---

## Phase 7 — Presence (glow bar + tray)

### 7.1 — Implement `src/clarity_v/presence/`

**Build:**

- `overlay.py` — the always-on-top glow bar (Qt window, sized to screen width × 6px)
- `state.py` — wired to StateManager from Phase 1.3
- `tray.py` — system tray icon, menu (Pause / Settings / Quit / About)
- Topmost dance delegated to `platform.make_window_topmost(hwnd)`
- Color-per-state from config (idle, recording, processing, commit_waiting, error)

**Verify:**

`tools/verify_presence.py`:

1. Launch presence + state manager.
2. Person-paced console-driven cycle through all five states: IDLE → RECORDING → PROCESSING → COMMIT_WAITING → ERROR → IDLE, holding each until the Person hits Enter in the console.
3. Person observes glow bar changes color through all 5 states.
4. Tray icon present, right-click shows menu.
5. Script asks Person: "Did you see the bar cycle through all five colors? y/n"

**Expected:** Person confirms "y".

(This is the only verification that depends on a Person's eyes. Don't fake it.)

---

## Phase 8 — Settings UI

### 8.1 — `src/clarity_v/settings/`

**Build:**

- Qt window with tabs: General, Presence, Keybinds, Dictionaries, Dictation Commands, Colors, Wake Words, Dictation Log
- Persists to `~/.clarity_v/settings.json`
- Live-apply: changing a color updates the glow bar immediately
- Mic selector with level meter
- Dictionary editor: list dictionaries, edit substitutions/macros/commands inline
- Keybind rebinding: click button, press key, captured
- Language selector: Auto-detect (default) / Lock to a specific language

**Verify:**

`tools/verify_settings.py`:

1. Launch settings.
2. Script prompts Person to: change idle color from default to bright red, save, observe glow bar.
3. Script prompts Person to: open Dictionary editor, add a macro, save, run dictation, say the macro trigger.
4. Assert dictation output contains the macro expansion.

**Expected:** color changed AND macro added AND macro fired.

### 8.2 — Voice Commands UI & Stateful Transforms

**Build:**
- `_VoiceCommandsTab` in `src/clarity_v/settings/window.py` for binding phases (during/after) to actions.
- `text_processor.py` for mid-dictation transformations (All Caps, Title Case, etc.) before paste.
- Inject `text_processor` into `dictation.py` pipeline.

**Verify:**
1. Open settings, add voice command "start caps" with action "All Caps" (phase: during).
2. Dictate "start caps hello world stop caps".
3. Assert transcript output is "HELLO WORLD".

---

## Phase 9 — End-to-end multi-language

Whole stack, two languages.

**Verify:**

`tools/verify_multilang.py`:

1. Person says "see vee go" + Portuguese sentence + "see vee over". Assert output is Portuguese.
2. Person says "see vee go" + English sentence + "see vee over". Assert output is English.
3. Same session, no restart between.

**Expected:** both work, language auto-detected per utterance.

---

## Phase 10 — Installer + cross-platform shake-out

### 10.1 — Windows installer (PyInstaller or Briefcase)

**Build:** `tools/build_windows.py` that produces a `.exe` installer.

**Verify:**

1. Build on Gonçalo's machine.
2. Copy `.exe` to a fresh Windows user account (or clean VM).
3. Install, launch, run Phase 9 verification.
4. **Person:** confirms it works on the fresh account / VM.

**Expected:** clean install + working dictation on a machine that wasn't the build machine.

### 10.2 — Linux X11 adapter

**Build:** `src/clarity_v/platform/linux_x11.py` (mostly copy windows.py, swap winsound → Qt audio).

**Verify:** Run on Linux X11 machine if available; otherwise mark as "not verified, contributor-welcome."

### 10.3 — macOS adapter

**Build:** `src/clarity_v/platform/macos.py`. Notarization queue.

**Verify:** Run on a Mac if available; otherwise mark as "not verified, contributor-welcome."

---

## Phase 11 — Public release

Only after Phases 0-9 are verified on Windows.

- Push to GitHub
- Write release notes
- v0.1.0 tag
- Open issue templates for bug reports / platform requests

---

## Verification hygiene

For every phase:

1. **Run the verification command** stated in the phase.
2. **Capture the full output.**
3. **Compare to the expected output.**
4. If matches: mark phase complete in TODO + report to Gonçalo with output excerpt.
5. If does not match: phase stays in progress. Identify root cause. Don't move to next phase.

Never report "Phase X complete" without quoting the verification output.

Never write `[x] Done` in the build plan based on what code "should do." Only based on what was observed.

If a phase's verification can't run (missing fixture, missing hardware, environment issue): the phase is **blocked**, not complete. Surface the blocker, don't fake completion.
