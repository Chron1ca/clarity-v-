# Clarity.V

**Your voice. Wherever you want it. Built to be used, shared, and forked.**

Clarity.V is a desktop voice dictation tool. It listens, transcribes, and pastes text wherever your cursor is — into any app, any text field, anywhere on your computer.

- **No API keys.** No subscription. No account.
- **No data sent anywhere.** Audio never leaves your machine. Transcription happens locally via [OpenAI Whisper](https://github.com/openai/whisper).
- **No telemetry you can't turn off.** The default is off.
- **Source code is the documentation.** Read it. Fork it. Trust through inspection.

## Hands-free in one conversation

Clarity.V closes the whole loop with your voice — not just the dictation part. You can stay in a single chat (Claude, ChatGPT, Gemini, Discord, anywhere) and never touch the keyboard:

1. Say `see vee go` → recording starts.
2. Say your message → it transcribes.
3. Stop talking (silence ends it) or say `see vee over` (instant) → transcription pastes at your cursor.
4. Say `send` (or `enter`) within 5 seconds → Ctrl+Enter fires, message goes.

Speak, pause, send. Speak, pause, send. Your hands stay where they are.

Most dictation tools only handle step 2. Clarity.V does all four.

[Quick start](#quick-start) · [How it works](#how-it-works) · [Features](#features) · [Profiles](#the-macro-dictionary) · [Privacy](#privacy) · [Architecture deep dive](ARCHITECTURE.md)

---

## Why this exists

Voice dictation built into operating systems is closed, slow, often cloud-dependent, and rarely good at anything except plain English in a clean room. The good local tools are either expensive (Dragon), tied to one app (every IDE's voice plugin), or research-grade and unfriendly (raw Whisper).

Clarity.V is the local Whisper engine, wrapped in the polish you'd expect from a paid product, given away because the model is already free and the wrapper is the part that should be free too.

## Who made this

Clarity.V is built by [**Chron1ca**](https://github.com/Chron1ca) (Gonçalo Parreira) — the same person behind [**U.Plane**](https://uplane.host), the commercial AI agent substrate. Clarity.V is the **free, open-source** counterpart in the same family of tools.

Why the free thing exists alongside the paid thing: U.Plane sells. Clarity.V doesn't. Releasing Clarity.V for free is the proof — verifiable in the source code in this repo — that the same hands behind a paid product can build genuinely-free local-first software that doesn't phone home, doesn't gate features, and doesn't depend on anyone's API. If you like Clarity.V enough to want hands-free dictation routed directly into AI agents, U.Plane is the upgrade path. If you don't, Clarity.V stays complete and free anyway.

Clarity.V and [U.Plane](https://uplane.host) are independent tools — each ships separately, each works on its own. If you only want free local dictation, Clarity.V is complete on its own.

## The pair (optional context)

Clarity.V is one of a small family of independent tools by the same author:

- **Clarity.V** — voice → text, anywhere on your computer. (You're reading about this one.) Free.
- **[U.Plane](https://uplane.host)** — an AI agent substrate: memory, claims, integration glue. Paid.

Clarity.V doesn't depend on U.Plane. They compose if you want; Clarity.V is complete on its own.

---

## Quick start

```bash
git clone https://github.com/your-handle/clarity-v
cd clarity-v
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
pythonw run.pyw
```

On first run, Clarity.V downloads the Whisper Medium model (~1.5 GB) to a local cache. After that, it's offline forever.

System requirements:

- **Windows 10/11** — full support, primary build target.
- **Linux (X11)** — full support after v1.1. `pynput` instead of `keyboard`, Qt audio instead of `winsound`. Mechanical swap.
- **Linux (Wayland)** — limited until v1.3. Global hotkeys and synthetic key events are restricted by Wayland's security model. Voice flow still works (no keybinds required); macros expand via clipboard; the `enter`/`send` voice-commit step needs `ydotool` or portal-based key injection. Working on it.
- **macOS** — planned v1.2. Requires you to grant Accessibility permission to Clarity.V (one-time, System Settings). Build will be notarized so you don't see scary warnings.
- **Python 3.10+** in all cases.
- **NVIDIA GPU recommended** (CUDA accelerates Whisper ~10x). Apple Silicon uses Metal via CTranslate2 (~5x over CPU). Plain CPU mode works on any platform; transcription is ~3-5x slower than CUDA but still usable.
- **~2 GB disk** for the Whisper Medium model + dependencies.
- **A microphone** (any standard input device — built-in is fine).

### Why the cross-platform caveats exist (real talk)

Open-source dictation tools fail in one of three ways: cloud-only (your audio leaves), Windows-only (half the market gone), or research-grade (works but no polish). Clarity.V refuses cloud-only and refuses no-polish; the remaining honest tradeoff is staged platform support.

The actual blockers per OS:

- **Linux/Wayland** restricts what desktop apps can do — by design, for good reasons. Global hotkey listeners and synthetic key events are gated behind portals or external tools like `ydotool`. We'll hit this fully in v1.3.
- **macOS** needs Apple's Accessibility permission (a user click) and code-signing/notarization ($99/year Apple Developer account, paperwork) so installers don't trigger Gatekeeper warnings. v1.2.

None of this is a fundamental limitation — Whisper, the wake-word model, the audio capture, the UI framework all run on all three OSes. The friction is in OS-level integrations (hotkeys, paste, overlay), which is what the `src/clarity_v/platform/` adapter layer abstracts. Adding a platform = adding one file under `platform/`.

---

## How it works

Plain English, no jargon:

1. Clarity.V sits quietly listening for two trained wake words (defaults: `cv_go` to start, `cv_over` to stop).
2. When you say `see vee go`, it starts recording.
3. You speak your message.
4. Recording ends when YOU say so: `see vee over` for an instant voice stop, or your configured stop keybind. The engine does not autonomously decide you're done. (Optional: if you prefer silence-auto-stop, increase **End by Silence** in Settings; default is off.) Clarity.V then transcribes what you said using a local Whisper model and pastes the result at your cursor.
5. For 5 seconds after the paste, Clarity.V keeps listening. If you say `enter` or `send`, it presses Ctrl+Enter for you — your message gets submitted, hands-free.
6. The dictionary swaps in proper spellings (your jargon, names, code), and the macro system can expand short phrases into multi-line templates (say `deffunc`, paste a full Python function skeleton).

That's the whole loop. No clicking, no typing, no browser tab, no cloud round-trip.

Want the precise state machine, the wake-detection internals, the trimming math, the hallucination filters? Read [ARCHITECTURE.md](ARCHITECTURE.md). It's all in there.

---

## Features

### Voice flow

- **Wake-word activation** — say `see vee go` (model `cv_go`), recording starts. Train your own wake word any time (see [TRAINING.md](TRAINING.md)).
- **Voice stop** — say `see vee over` (model `cv_over`) for an instant cut-off. The engine does NOT auto-end recording on silence by default — you decide. If you want silence-auto-stop, enable **End by Silence** in Settings.
- **Voice commit** — say `enter` or `send` within 5 seconds of paste, Clarity.V submits (Ctrl+Enter equivalent).
- **Mid-dictation insertions** — say `new paragraph`, `new line`, `tab` while dictating; the dictionary rewrites these to the matching character before paste. (True mid-dictation key combos like `delete that` are planned for v1.x.)

### Speaks your language

Clarity.V uses Whisper's full multi-language model (Medium, 99 languages). The default mode is **auto-detect per utterance**: you speak Portuguese, you get Portuguese. You switch to English mid-conversation, Clarity.V follows. No language pin, no setup, no "switch to Spanish mode."

Tested daily on PT + EN by the author. Works on the other 97 too; reports welcome.

### Dictionary Profiles

Each dictionary profile has three layers:

- **Substitutions** — phrase → phrase. Fix Whisper mishears, swap in jargon. Example: `git hub` → `GitHub`.
- **Macros** — phrase → multi-line template. Say a short trigger word, get a full code snippet, boilerplate, email signature, anything.
- **Voice Commands (Action Dictionary)** — phrase → action. 
  - **Commit Actions**: Say `enter` to trigger `Ctrl+Enter`, or `delete all` to trigger `Ctrl+A, Backspace`. Custom keybinds are fully supported in the UI!
  - **Mid-Dictation Transforms**: Say `all caps` to start capitalizing your sentence, and `stop caps` to return to normal. Or say `capitalize next` to uppercase the next word.

Dictionary profiles inherit (`extends: "default"`). They ship with `default.json` (English prose) and `python.json` (Python coding dictionary). You can create your own custom dictionaries and switch them instantly with a single click or keyboard shortcut.

Example coding macros (already in `dictionaries/python.json`):

| Say          | Get                                                  |
| ------------ | ---------------------------------------------------- |
| `deffunc`    | `def function_name(args):\n    pass`                 |
| `tryblock`   | `try:\n    pass\nexcept Exception as e:\n    pass`   |
| `main block` | `if __name__ == "__main__":\n    main()`             |
| `class block`| `class ClassName:\n    def __init__(self):\n    pass`|
| `for loop`   | `for i in range(10):\n    pass`                      |
| `with open`  | `with open("path", "r") as f:\n    pass`             |
| `list comp`  | `[x for x in iterable]`                              |

Coding dictionaries are programmable. Add your own.

### Presence Overlay

Clarity.V provides visual cues on the desktop:
- **Glow Bar**: A small ambient glow at the edge of your screen that shows what the engine is doing right now — idle (ready), recording, transcribing, post-paste commit waiting, or error/cancelled. Each state has a fully configurable color. Thickness, peak brightness/transparency, and edge positioning (Top, Bottom, Left, Right, or Freeform coordinates) can be adjusted in the settings.
- **Floating Start/Stop Button**: A draggable circular widget overlay showing the current engine state. Left-clicking toggles dictation; right-clicking opens a full app control menu (Pause/Resume, Dictionaries, snap to top/bottom corners, toggle visual elements, or Quit). Its diameter size and custom X-Y coordinate overrides are fully configurable.
- **System Tray Icon**: A standard icon in the taskbar notification area for quick access to menus and dialogs.

Both the glow bar and floating button are always-on-top, click-through (for the glow bar), take no focus, and never steal keyboard input from your active app.

### Settings UI

Clarity.V features a spacious, glassmorphic settings panel structured into dedicated tabs:
- **General**: Choose your mic input device, select a model size, force transcription language lock, adjust minimum/maximum timing windows, configure the Whisper initial prompt, and toggle sound cues.
- **Presence Overlay**: Toggle the edge glow bar and adjust its thickness, brightness, and position (Top, Bottom, Left, Right, or Freeform). Toggle and resize the floating start/stop button or system tray icon.
- **Keybinds**: Set custom global keyboard hotkeys to start and stop dictation, push-to-talk (PTT), cancel dictation, and pasting the last transcription.
- **Dictionaries**: Select your active dictionary profile, bind specific hotkeys to switch profiles on the fly, create new ones, and manage the Vocabulary Blacklist for custom hallucination filtering.
- **Voice Editing**: Manage formatting controls (casing, bold, italic, code mode), post-paste actions (Send/Enter, Select All, Delete All), and symbol/typing shortcuts in collapsible card views.
- **Colors**: Customize the exact RGB/alpha palette colors representing each active engine state.
- **Voice Activation**: Toggle continuous wake word detection, configure sensitivity thresholds, and launch the **Efficacy Enhancement Wizard** to train existing models on your own voice.
- **Dictation Log**: Review the most recent 100 transcriptions and click to copy them to the clipboard.
- **Engine Console**: Monitor live, color-coded backend messages, transcription activities, and runtime logs directly in the user interface.

### Mic selector

List of input devices, sample rates handled per-device, live level meter so you can see Clarity.V is hearing you before you trust it.

### Voice training *(optional)*

Train your own wake words so they fire reliably for your voice in your room. The bundled `cv_go` + `cv_over` are calibrated against the author's voice; you can recalibrate or train completely new phrases via [TRAINING.md](TRAINING.md). Optional — Whisper itself doesn't need training; only the wake-word detector benefits.

### Keybinds *(optional, alongside voice flow)*

- **PTT (push-to-talk)** — hold a key, speak, release.
- **Start/stop toggle** — press once start, press once stop.
- Configurable, rebindable. Voice flow doesn't require them; they exist for noisy environments or when you don't want voice activation.

### Hallucination filter

Whisper hallucinates on silence and noise. Clarity.V catches four known patterns:

- **Known-phrase blacklist** — `"thanks for watching"`, `"please subscribe"`, `"thank you for listening"`, and the rest of YouTube's transcription corpus that Whisper learned to emit when fed silence. Users can extend this list with the **Vocabulary Blacklist** in the Dictionaries settings tab, adding custom phrases that should be treated as hallucinations.
- **Repeat-loop filter** — same sentence appearing 2+ times in one transcription is Whisper looping on noise. First occurrence kept, repeats dropped.
- **Wake-phrase strip** — if the wake word leaked through into the recording (rare, happens on partial detection), regex it out before paste.
- **Prompt-prefix filter** — if the transcription is a prefix of the Whisper initial prompt (a common silence-on-primed-model pattern), it's discarded as a hallucination.

---

## Privacy

The short version: **your audio never leaves your computer**.

- All transcription is local (Whisper, faster-whisper).
- Wake-word detection is local (OpenWakeWord).
- No network calls during normal operation. Run with the network unplugged, it works.
- No analytics, telemetry, or crash reporting by default.

The long version, with code references: [PRIVACY.md](PRIVACY.md).

---

## The paid path (optional, not required)

Clarity.V dictates into any text field — that's the free version, complete and forever.

The paid upgrade is **direct integration with [U.Plane](https://uplane.host)**. Instead of dictating *into* a chat textbox, your voice routes *directly* into U.Plane's agent context — no copy-paste loop, no "click into the textbox first." Useful only if you're already a U.Plane user. Buying U.Plane gets you the integration. Clarity.V itself stays free either way.

If you don't use U.Plane, you'll never notice the integration hook. It's a single optional setting.

---

## What's in this repo

```text
clarity-v/
├── README.md              ← you are here
├── ARCHITECTURE.md        ← voice activation deep dive, state machine, every piece
├── PRIVACY.md             ← exact data flow, what leaves the machine (nothing)
├── TRAINING.md            ← train your own wake word, end-to-end
├── CONTRIBUTING.md        ← how to add a platform / backend / dictionary
├── BUILD_PLAN.md          ← phase-by-phase build plan + verification gates
├── CHANGELOG.md           ← versioned change history
├── LICENSE                ← MIT
├── pyproject.toml         ← ruff + pytest config (line-length 88)
├── requirements.txt       ← runtime Python dependencies
├── run.pyw                ← entry point (windowed; no console)
├── wake_config.json       ← runtime wake-word config (name, threshold, role)
├── src/clarity_v/           ← all source
│   ├── app.py             ← wires engine + presence + settings + platform
│   ├── dictation.py       ← state-machine orchestrator (wake → record → transcribe → paste)
│   ├── whisper_engine.py  ← faster-whisper wrapper, language=None default
│   ├── audio.py           ← sounddevice capture
│   ├── wake.py            ← OpenWakeWord wake detection (role-routed: start/stop)
│   ├── dictionary.py      ← substitution + macro expansion engine + hot reload
│   ├── commit.py          ← post-paste voice-commit window (5 s default)
│   ├── filters.py         ← hallucination filters (known-phrase, repeat-loop, wake-strip)
│   ├── buffer.py          ← LastDictationBuffer (separate from OS clipboard)
│   ├── dictation_log.py   ← opt-in JSONL log with size rotation
│   ├── sounds.py          ← activation/deactivation cue playback
│   ├── state.py           ← thread-safe state machine + subscribers
│   ├── presence/          ← glow bar + tray + floating start/stop button
│   ├── settings/          ← Qt 9-tab settings dialog (General, Presence Overlay, Keybinds, Dictionaries, Voice Editing, Colors, Voice Activation, Dictation Log, Engine Console)
│   └── platform/          ← per-OS adapters (hotkeys, paste, overlay, sound)
│       ├── _base.py       ← shared interface — what every platform must implement
│       └── windows.py     ← v1.0 reference implementation (Win32 + pynput)
├── dictionaries/          ← shipped dictionary profiles
│   ├── default.json       ← English prose, voice commands (extends nothing)
│   └── python.json        ← Python coding macros (extends default)
├── models/                ← shipped wake-word ONNX files
│   └── wake_words/        ← cv_go.onnx + cv_over.onnx (trained, calibrated)
├── tools/                 ← interactive verification + training scripts
│   ├── verify_audio.py    ← Phase 3: mic + capture
│   ├── verify_whisper.py  ← Phase 2: STT against EN + PT fixtures
│   ├── verify_wake.py     ← Phase 4: wake-word detection
│   ├── verify_dictation.py← Phase 5: full E2E into a text editor
│   ├── verify_presence.py ← Phase 7: glow bar + tray
│   ├── run_voice_tests.py ← one command, walks all phases in order
│   └── training/          ← wake-word training pipeline (own venv recommended)
├── scripts/               ← developer helpers (dev.py check / fix / test)
├── tests/                 ← pytest unit tests (no mic required)
├── packaging/             ← PyInstaller spec for Windows builds
├── assets/sounds/         ← activation/deactivation cues (WAV)
└── .github/               ← issue templates + CI workflow
```

Other platforms (`linux_x11.py`, `macos.py`, `linux_wayland.py`) are **planned**, not yet on disk — see CONTRIBUTING.md if you want to ship one.

Everything is plain Python. No bundled binaries (except optional ffmpeg, which you can replace with your own). No obfuscation.

---

## Dependencies (what runs on your machine and why)

- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — CTranslate2-accelerated Whisper. Local STT. The actual transcription work.
- **[OpenWakeWord](https://github.com/dscripka/openWakeWord)** — local wake-word detection. ONNX neural net, ~5 MB models.
- **[sounddevice](https://python-sounddevice.readthedocs.io/)** — audio input from your microphone via PortAudio.
- **[numpy](https://numpy.org/)** — audio array manipulation.
- **[pyperclip](https://github.com/asweigart/pyperclip)** — clipboard read/write for the paste-at-cursor mechanism. Cross-platform.
- **[pynput](https://pynput.readthedocs.io/)** — global hotkey listener and synthetic keyboard events (Ctrl+V paste, Ctrl+Enter commit, optional PTT keybinds). Cross-platform on Windows/X11/macOS; Wayland needs workarounds.
- **[PySide6](https://doc.qt.io/qtforpython-6/)** — settings UI, glow bar overlay, audio cues. Cross-platform.
- **[requests](https://requests.readthedocs.io/)** — only invoked if you enable the optional U.Plane integration. Otherwise never imported at runtime.

Total install footprint: ~3-4 GB (Whisper Medium + faster-whisper's CTranslate2 runtime + dependencies). The Whisper model is the bulk.

---

## Status

**v1.0 in build, June 2026.** First public release coming. Watch this repo for releases.

The dictation engine, wake detection, hallucination filters, and core flow are extracted from a working system that's been the author's daily driver for ~9 months. The polish layer (settings UI, mic selector, voice training, installer) is new work on top.

## Contributing

Bug reports and PRs welcome. The architecture document is the place to start — read it, find a place where it could be better, propose a change. Drive-by improvements (better wake models, more language coverage, better hallucination filtering, dictionary profiles for languages other than English/Python) are especially appreciated.

## License

MIT. See [LICENSE](LICENSE). Use it, fork it, sell something built on it. Attribution appreciated, not required.

---

Made by [Chron1ca](https://github.com/Chron1ca) (Gonçalo Parreira).
