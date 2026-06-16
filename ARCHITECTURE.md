# Clarity.V Architecture

The voice-activation flow is not "transcribe audio, paste text." There's a state machine, multiple audio buffers, two distinct voice-input mechanisms with very different jobs, and a discipline of cleanup paths that every short-circuit must honor.

This document explains how the dictation engine actually works. If you're contributing a platform, you don't need to read this — see [CONTRIBUTING.md](CONTRIBUTING.md). If you're working on the core engine, dictionary, or filters, start here.

---

## The two voice-input mechanisms

Clarity.V uses two distinct mechanisms for understanding voice, with very different properties:

### OpenWakeWord (the wake detector)

- Runs continuously on every audio chunk (~250 ms at 16 kHz / 4000 samples).
- Fires only on the specific phrases its ONNX models are trained on.
- Cheap. Can run in the background indefinitely.
- Cannot recognize arbitrary speech — it's a *phrase classifier*, not a transcriber.

### Whisper (the transcriber)

- Runs on a captured audio buffer, returns the transcript.
- Recognizes any spoken language and any phrase.
- Not streaming-capable in the standard sense. You feed it a complete buffer; it returns text.
- Used twice per dictation: once for the main message, once for the post-paste action window.

**The split matters.** "enter", "send", "new paragraph" — these are NOT wake words. They're matched by transcribing the post-paste audio and string-matching the result against the dictionary's `voice_commands` table. A common mistake is to assume the wake detector handles them; it can't, unless we train a custom OpenWakeWord model per command (and that's not the v1 design).

---

## State machine

```text
                ┌─────────────────────────────────────────────────┐
                │                                                 │
                ▼                                                 │
            ┌──────┐  wake fires       ┌──────────┐  stop signal  │
            │ IDLE ├──────────────────▶│ RECORDING├───────────────┤
            └──────┘                   └──────────┘               │
                │                            │                    │
                │                            ▼                    │
                │                      ┌────────────┐             │
                │                      │ PROCESSING │             │
                │                      │ (transcribe│             │
                │                      │  + paste)  │             │
                │                      └─────┬──────┘             │
                │                            │                    │
                │                            ▼                    │
                │                  ┌──────────────────┐           │
                │                  │ COMMIT_WAITING   │           │
                │                  │ (10s window for  │           │
                │                  │  enter/send)     │           │
                │                  └────────┬─────────┘           │
                │                           │                     │
                │                           ▼                     │
                │     ┌──────────────────────────────────┐        │
                └─────┤ window closed / commit fired     │────────┘
                      └──────────────────────────────────┘
```

**Five states** in the `State` enum (see [src/clarity_v/state.py](src/clarity_v/state.py)). The bar is a presence indicator: it shows the program is on (IDLE) and changes color when something specific is happening.

- **`IDLE`** — program is on, ready. The bar's resting color. Default soft blue. Set alpha=0 in Settings if you want the bar invisible at rest.
- **`RECORDING`** — audio is being captured for the main message. Default green.
- **`PROCESSING`** — Whisper is transcribing; paste is happening. Default orange.
- **`COMMIT_WAITING`** — post-paste 5-second window for "enter" / "send". The audio paste-pip marks its start. Default teal.
- **`ERROR`** — abrupt stop. Covers both system error AND user cancel (Ctrl+Shift+Q); the two are distinguishable via `info["cancelled"]`. Default red.

(Defaults from [src/clarity_v/presence/colors.py](src/clarity_v/presence/colors.py); every state's color is editable in Settings → Colors.)

State transitions are not strictly enforced — any state can move to `IDLE` (used as a hard reset on errors). The dictation orchestrator owns which transitions are valid in the happy path.

---

## The full dictation cycle

Step by step, with the audio buffers and the cleanup discipline:

### 1. Idle

- `WakeDetector.feed(chunk)` runs on every audio chunk.
- The audio buffer is empty.
- State: `IDLE`.
- No transcription cost; just the wake-model neural net at ~5 MB.

### 2. Wake fires

- `WakeDetector` returns a `WakeEvent` with the model name, confidence score, and **chunk index** (position in the current buffer where the detection happened).
- A cooldown check prevents double-fires within ~500 ms.
- State → `RECORDING`.
- Audio buffer starts collecting chunks.
- Glow bar transitions color.

### 3. Recording

- Every audio chunk appends to the buffer.
- Wake model **continues running** on each chunk (so we can detect a stop-wake or a start-wake re-fire while recording).
- A simple energy threshold tracks silence in parallel — if the Person has opted into silence-stop by setting `silence_seconds_to_stop > 0` in Settings, audio dropping below threshold for that many seconds ends the recording. Default is **0 (disabled)**: the engine never autonomously decides you're done.

### 4. Stop signal

The recording ends in one of four ways, in v1:

- **Silence detection** (opt-in; default OFF) — N seconds of sub-threshold audio. Some Persons want this; many don't. The engine never assumes — `silence_seconds_to_stop` must be set > 0 in Settings to enable. The AI does not decide when your message is done.
- **Stop-wake fire** (instant) — say the configured `role=stop` wake word (default `cv_over`, phrase "see vee over"). The detector fires, the recording ends immediately, no silence wait, no wake-phrase trim (the stop word was spoken separately from the message).
- **Start-wake re-fire** (toggle, the Shelly pattern) — say the `role=start` wake word again (default `cv_go`, phrase "see vee go"). The detector's chunk index lets us trim the wake-word audio off the buffer's end.
- **Hotkey toggle** — if PTT/toggle keybinds are enabled, the Person can stop via key.

State → `PROCESSING`.

The router lives in [src/clarity_v/dictation.py](src/clarity_v/dictation.py) `_handle_wake`: it dispatches on the WakeEvent's `role`. Start wakes during idle begin recording; stop wakes during recording end it (clean stop, no trim); start wakes during recording trigger the re-fire toggle (with trim).

### 5. Wake-phrase trim (start re-fire only)

If the recording ended via the start-wake re-fire path, the last ~6 chunks (~1.5 s) before the detection chunk index almost certainly contain the wake word audio. Trim those off the main buffer; keep the trimmed portion separately in case action words were spoken immediately after. (Stop-wake fires DON'T trim — the stop word was a separate utterance.)

```text
Main buffer:   [chunk_0, chunk_1, ..., chunk_(det-6) | chunk_(det-6+1), ... chunk_(det)]
               └─────── kept ────────────────────────┘└──── trimmed ────────────────────┘
                                                      (may contain action words said
                                                       right after the wake word)
```

The trim chunk count is configurable; 6 chunks works for "see vee go" / "see vee over" (~1.2 s). Longer wake phrases need more.

### 6. Whisper transcribe (main message)

- Convert buffer to `float32 / 32768.0`.
- Call `whisper.transcribe(audio, language=None, ...)` — **language is None**, never pinned to a single language. Multi-language initial prompt primes the tokenizer for EN + PT.
- Receive `segments` and `info`. Build `raw_text`; capture `info.language` for logging.

### 7. Filter chain

In order (see [src/clarity_v/filters.py](src/clarity_v/filters.py)):

1. `strip_repeated_sentences` — same sentence 2+ times means Whisper looped on silence/noise. First occurrence kept, subsequent dropped.
2. `strip_known_hallucinations` — known phrases in `HALLUCINATIONS` list (English subscribe-prompts, Portuguese equivalents, etc.) full-match or trailing-strip.
3. `strip_prompt_prefix_hallucination` — if the transcribed text is a prefix of the Whisper initial prompt (a common pattern when Whisper is primed with an initial prompt and fed silence), discard it.
4. `strip_wake_phrase` — if the wake phrase leaked into the main transcription (rare; happens on partial detection), regex it out.

If filtered text is empty, the entire transcription was hallucination. Cleanup: state → `IDLE`, no paste.

### 8. Vocabulary correction (substitutions)

`Dictionary.apply_substitutions(text)` runs single-pass alternation regex with longer keys first. `"git hub"` becomes `"GitHub"`, case-insensitive, word-boundary-aware.

### 9. Macro expansion

`Dictionary.expand_macros(text)` looks for macro triggers in the cleaned text. If the Person said `"deffunc"`, expand to the Python function template. Same single-pass regex with longer triggers first.

### 10. Paste

`platform.paste_text(final_text)`. On Windows: save existing clipboard, copy `final_text`, send Ctrl+V, restore clipboard after 200 ms. Platform-specific variations.

### 11. Commit window opens

State → `COMMIT_WAITING`. The trimmed audio from step 5 (if any) becomes the start of a new buffer. Audio capture continues for N more seconds (default 5; configurable to 10).

### 12. Commit transcribe

After the window closes:

- Concatenate the trimmed-portion-as-seed + post-paste audio into one buffer.
- `whisper.transcribe(buffer, language=None, beam_size=1, ...)` — `beam_size=1` is fast (action transcripts are short; quality matters less).
- Apply the same filter chain.
- Pass cleaned text to `Dictionary.match_voice_command(text, phase="after")`.

### 13. Voice command dispatch

If a command matches with `phase="after"`:

- Look up the action. For `enter` / `send` the action is `submit`, which means `Ctrl+Enter` via the platform adapter.
- For `new paragraph` (which is `phase="during"`, so wouldn't fire here — but as an example): insert `\n\n` via the platform adapter.
- Execute via `platform.send_key_combo(combo)`.

### 14. Cleanup

State → `IDLE`. Audio buffer cleared. Wake detector listening again. Glow bar returns to idle color.

**Every short-circuit path must end with the same cleanup.** Empty transcription, only-hallucination, too-short audio, exception — all paths reset state to IDLE explicitly. The state machine never leaks.

---

## Voice commands during dictation (the honest picture)

There are three places voice commands can fire, and they have very
different cost/capability profiles. The dictionary's `voice_commands`
entries each have a `phase` field that picks which mechanism handles them.

### Post-paste commands (`phase: "after"`) — fully supported in v1

After the message is pasted, Clarity.V captures another ~5 seconds of
audio, runs Whisper on it, and string-matches the transcript against
`voice_commands` where `phase: "after"`. This is how `enter` / `send`
fire the Ctrl+Enter that submits a chat message.

Cost: one extra short Whisper transcribe per dictation cycle.
Capability: anything — Whisper hears whatever the Person says.

### Substitution-style "during" commands — supported via the dictionary

Some phrases that *feel* like mid-dictation commands are really
post-transcription text substitutions:

- "new paragraph" → `\n\n`
- "new line" → `\n`
- "open paren" → `(`

These work today via the `macros` table or `voice_commands` entries
with `action: "insert"`. The Person says the phrase as part of their
utterance ("I think we go this way new paragraph and then the next
section"), Whisper transcribes the whole thing, and the dictionary
swap replaces `new paragraph` with `\n\n` before paste.

Cost: zero — same path as any other dictionary substitution.
Capability: text-only insertion. No key combos. No state changes.

### True mid-dictation commands (Stateful Transforms) — supported in v1

A command like `all caps` or `stop caps` or `capitalize next word` fires DURING recording, but without the cost of periodic micro-transcribes.

Clarity.V achieves this via the **Stateful Text Processing Engine** (`text_processor.py`). 

1. The person says the entire sentence: "I think we go this way all caps and then the next section stop caps".
2. Whisper transcribes the whole buffer.
3. Before the text is pasted, `process_text_transforms` splits the transcript by the configured trigger phrases (e.g. `all caps`, `stop caps`).
4. It iterates through the text chunks, turning capitalization modes on and off as it hits the trigger boundaries. The triggers themselves are stripped out.
5. The final formatted text is pasted.

Cost: Zero overhead during audio capture. Negligible string manipulation overhead post-transcription.
Capability: Powerful casing, formatting, and text-state manipulation. (Does not support mid-dictation OS-level key combos like Ctrl+Z — those are still deferred to v1.x via periodic micro-transcribes).

### Where this lives in the codebase

- `clarity_v/dictionary.py` — defines and matches `voice_commands` by phase.
- `clarity_v/commit.py` — runs the post-paste window (`phase: "after"`).
- `clarity_v/dictation.py` — applies substitutions + macros + text processor transforms.
- `clarity_v/text_processor.py` — stateful formatting engine for `phase: "during"` and `action: "transform"`.

---

## Dictionary

Three categories of entries (see [src/clarity_v/dictionary.py](src/clarity_v/dictionary.py) and [dictionaries/default.json](dictionaries/default.json)):

```json
{
  "name": "default",
  "extends": null,
  "substitutions": { "git hub": "GitHub" },
  "macros":        { "deffunc": "def function_name(args):\n    pass" },
  "voice_commands": {
    "stop":  { "action": "end_dictation", "phase": "during" },
    "enter": { "action": "submit",        "phase": "after"  },
    "new paragraph": { "action": "insert", "text": "\n\n", "phase": "during" }
  }
}
```

- **`substitutions`** — phrase → phrase. Whisper mishears and personal jargon.
- **`macros`** — phrase → multi-line template. Coding dictionaries live here.
- **`voice_commands`** — phrase → action dict, with `phase: "during"` (mid-dictation, currently only handled via custom wake models or streaming Whisper — future) or `phase: "after"` (post-paste window — the standard case).

Dictionaries inherit via `extends`. `python.json` extends `default.json`; child entries override parent entries by key. Loaders detect circular extends and raise.

Hot reload via `start_watching()` — daemon thread polling source-file mtimes; reloads on change, fires registered callbacks. Bad JSON during a reload keeps the previous in-memory state intact; never crashes.

---

## Filters (deep dive)

### `strip_repeated_sentences`

Whisper's most common hallucination on silence is repeating a single phrase. The filter splits on sentence boundaries (`. ! ? \n\n`), normalizes for comparison (lowercase, collapsed whitespace, no punctuation), counts occurrences, and drops everything after the first match.

`"Hello. Hello. Hello."` → `"Hello."`
`"First. Second. First."` → `"First. Second."` (mid-occurrence repeat dropped)

### `strip_known_hallucinations`

Two-step:

1. **Full match** — entire text is a known hallucination phrase (lowercased, trailing punctuation stripped) → return empty.
2. **Trailing match** — text *ends* with a known phrase → strip the phrase and keep the rest. The real sentence's terminal punctuation (`.`, `?`, `!`) is preserved.

The `HALLUCINATIONS` list covers English, Portuguese, Spanish, French, German YouTube training-data artifacts.

### `strip_prompt_prefix_hallucination`

When Whisper is primed with an `initial_prompt` and receives silence or noise, it commonly echoes part of the prompt back. This filter normalizes both the transcription and the prompt (lowercase, letters/digits/spaces only), then checks if the normalized transcription is a prefix of the normalized prompt (and at least 4 characters long). If so, the text is discarded as a hallucination.

### `strip_wake_phrase`

Word-boundary regex strip of any configured wake phrases. Used as the last filter in the pipeline. Crucially, it translates underscores in wake model names (e.g. `cv_over`) to spaces when matching (`cv over`), because Whisper will naturally transcribe the audio as separate English words rather than outputting the exact underscored token. Multi-space collapse afterward.

---

## Platform adapter

The `src/clarity_v/platform/_base.py` interface — see [CONTRIBUTING.md § Add a platform](CONTRIBUTING.md#add-a-platform) for the contributor flow.

What every platform must implement:

- `register_hotkey(combo, on_press, on_release=None, suppress=True)`
- `unregister_all_hotkeys()`
- `send_key_combo(combo)` — synthesize key events
- `paste_text(text)` — text at cursor in focused app
- `play_sound(wav_path)` — async cue
- `make_window_topmost(hwnd)` — keep glow bar on top

The Windows reference (`platform/windows.py`) uses:

- `pynput.keyboard.GlobalHotKeys` for press-only hotkeys
- `pynput.keyboard.Listener` for press+release (PTT) hotkeys
- `pynput.keyboard.Controller` for synthesized input
- `pyperclip` for clipboard
- `winsound.PlaySound(SND_ASYNC)` for audio cues
- `win32gui.SetWindowPos(HWND_TOPMOST)` re-asserted every 500 ms

Linux X11 will use the same pynput + Qt audio + a smaller win32-replacement. macOS adds Accessibility permission handling. Wayland needs a portal-based approach for key synthesis and hotkeys.

### Keystroke Simulation Timing Cadence

To ensure compatibility with a wide range of desktop apps (specifically basic text controls like Windows Notepad), the synthetic key-press engine in `WindowsAdapter.send_key_combo` implements a precise timing delay. 

When a keyboard shortcut is triggered (such as sending `ctrl+enter` to commit dictation):
1. Modifier keys (e.g. `ctrl`) are pressed down first.
2. The main key (e.g. `enter`) is pressed down next.
3. The engine pauses for exactly `0.02 seconds` (`time.sleep(0.02)`) while holding all keys. This short delay ensures the target application's message loop registers the modifier states. Without this pause, rapid key press/release transitions often drop modifier states in lightweight GUI controls, failing to trigger the shortcut.
4. Keys are released in reverse order.
5. On failure/exceptions, a best-effort release is executed on all pressed keys to prevent modifier keys from getting stuck in the OS.

---

## Process Lifecycle & Chromium Management

Clarity.V runs a single-instance core engine alongside a modern web-based Settings UI rendered inside a desktop shell via Qt WebEngine (`QWebEngineView`). Because Qt WebEngine spawns multiple Chromium helper processes (`QtWebEngineProcess.exe` or associated sub-processes), careful lifecycle and IPC management is required:

### QWebEngine Process Leaks Prevention

To prevent Chromium helper processes from leaking and accumulating in memory when the Settings window is opened and closed:
1. **Delete on Close**: The `SettingsDialog` widget is constructed with the `Qt.WA_DeleteOnClose` attribute enabled. This instructs Qt to immediately deallocate the C++ dialog object when the user closes the window.
2. **Explicit WebEngine Teardown**: In `SettingsDialog.closeEvent(event)`, we manually release resources:
   - Disconnect the `QWebChannel` from the page (`setWebChannel(None)`) to break the JS-to-Python communication bridge.
   - Detach the `QWebEngineView` from its layout parent (`setParent(None)`).
   - Call `deleteLater()` on both the `QWebEnginePage` and `QWebEngineView`.
   This ensures that Chromium's subprocesses are terminated instantly when the dialog is closed, maintaining a completely flat process footprint.
3. **Application Exit Cleanup**: On application quit, the app sweeps top-level widgets to find and close any active `SettingsDialog` instances first. This releases any active modal loops (`dlg.exec()`) and allows the main application process to exit cleanly.

### Single-Instance IPC Mechanism

Clarity.V guarantees that only one core engine runs at any time, protecting system hotkeys and audio streams:
1. At startup, the app creates a `QLocalServer` named `"ClarityV_IPC"`.
2. Before starting, it attempts to connect to this server name using `QLocalSocket`.
3. If connection succeeds (with a 500ms timeout), it means another instance is already running. The new process writes `"show_settings"` to the socket to request the active instance to open/focus the Settings dialog, and then exits immediately with code `0`.
4. If connection fails, the socket is discarded, the server is registered to listen on `"ClarityV_IPC"`, and the main loop begins.
5. The active instance listens for incoming local socket connections. When a message is received, it schedules a single-shot timer to invoke `open_settings()`, bringing the existing Settings window to the foreground and raising/activating it.

---


## What's where, one-line guide

- **`src/clarity_v/filters.py`** — pure functions for hallucination / repeat / prompt-prefix / wake-phrase stripping.
- **`src/clarity_v/dictionary.py`** — JSON loader, extends chain, substitutions, macros, voice commands, hot reload.
- **`src/clarity_v/state.py`** — `State` enum + thread-safe `StateManager` broadcaster.
- **`src/clarity_v/whisper_engine.py`** — faster-whisper wrapper. `language=None` default. Returns `TranscriptionResult` dataclass.
- **`src/clarity_v/audio.py`** — microphone capture via sounddevice.
- **`src/clarity_v/wake.py`** — OpenWakeWord wrapper. Multi-model, threshold, role (start/stop), cooldown, chunk-index.
- **`src/clarity_v/dictation.py`** — the state-machine orchestrator. Routes wake events by role, applies the filter chain, manages the cleanup discipline.
- **`src/clarity_v/commit.py`** — post-paste window: Whisper transcribe + voice-command match (phase=after).
- **`src/clarity_v/buffer.py`** — LastDictationBuffer (separate from the OS clipboard).
- **`src/clarity_v/dictation_log.py`** — opt-in JSONL log with size-based rotation.
- **`src/clarity_v/log_capture.py`** — thread-safe log capture utility with memory ring-buffer for settings console.
- **`src/clarity_v/sounds.py`** — activation / deactivation / paste cue playback via the platform adapter.
- **`src/clarity_v/presence/`** — glow bar overlay, tray icon, floating start/stop button, state subscriber.
- **`src/clarity_v/settings/`** - 9-tab Qt settings dialog (General, Presence Overlay, Keybinds, Dictionaries, Voice Editing, Colors, Voice Activation, Dictation Log, Engine Console) backed by a JSON file.
- **`src/clarity_v/platform/`** — OS adapters. `_base.py` is the contract; `windows.py` is the v1.0 reference.

---

## The standing rule (build discipline)

**Completion is the only metric.** Every module ships with a verification command and an expected output. The module is not done until the verification ran and matched. See [BUILD_PLAN.md](BUILD_PLAN.md) for the phase-by-phase plan with verification gates.

If you're sending a PR that adds or changes engine behavior, follow the same discipline: prove it works with captured output, not "should work" assertions.
