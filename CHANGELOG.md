# Changelog

All notable changes to Clarity.V.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [SemVer](https://semver.org/).

## [Unreleased] — v0.1.0 (in progress)

The first public release. Local-first voice dictation for the desktop.

### Added

- **Dictation engine** — Whisper-powered local STT with state machine
  (idle → recording → processing → commit-waiting → idle), silence
  detection for natural stop, wake-word re-fire as alternative stop.
- **Auto language detection** — `language=None` by default; Whisper Medium
  speaks 99 languages, never pinned to one.
- **Three-layer hallucination filter** — sentence-repeat dedupe,
  known-phrase blacklist (EN + PT + ES + FR + DE), wake-phrase regex strip.
- **Macro dictionary** — JSON-backed substitutions, multi-line macros
  (coding-dictionary capable), voice commands with `phase` gating
  (`during` dictation vs `after` paste), `extends` chain for profiles,
  hot-reload via background file watcher.
- **Voice-commit window** — after paste, listens 5 s (configurable) for
  `enter` / `send` / `new paragraph` / etc., matched via post-paste
  Whisper transcribe + dictionary lookup.
- **Voice Commands UI** — Interactive table in Settings to configure trigger phrases for commit window actions (like triggering OS keyboard shortcuts, inserting text, or pressing Ctrl+Enter).
- **Stateful Text Transformations Engine** — Intercepts voice dictation before pasting to apply live formatting changes like "start caps", "stop caps", and "capitalize next word".
- **Paste-last-dictation keybind** — a configurable keybind (e.g.,
  `ctrl+shift+v`) re-pastes the most recent transcription at the
  cursor. Useful when the original paste landed in the wrong place.
  The buffer is independent of the OS clipboard — your normal
  `Ctrl+C` / `Ctrl+V` keeps working untouched.
- **Persistent dictation log** — opt-in, JSONL format, append-only,
  rotates at 500 KB per file (`dictation_log_001.jsonl`,
  `_002.jsonl`, ...). UTF-8, preserves multi-language text (PT, JA,
  newlines) cleanly. Lives at `~/.clarity_v/dictation_logs/`.
- **Wake-word detection** — OpenWakeWord wrapper with per-model `role`
  routing (`start` to begin dictation, `stop` to end it). Ships with two
  trained custom models: `cv_go` (start, phrase "see vee go") and
  `cv_over` (stop, phrase "see vee over"). Falls back to OpenWakeWord's
  bundled `hey_jarvis` if both ONNX files are missing on disk.
- **Custom wake-word training pipeline** - `tools/training/`:
  - New **Interactive Training Wizard** (`wizard.py`) automates the entire ML setup and training process via a detached CLI.
  - Generates 5,000+ synthetic TTS samples locally.
  - Prompts for and automatically records/augments personal voice samples.
  - Trains, calibrates, and validates custom ONNX wake words.
  - Added a **UI warning and confirmation dialog** in the settings web interface before launching the wizard to prevent unexpected 17.5 GB downloads.
  - Fixed path resolution, Windows command quoting, and PyInstaller frozen execution support in the wizard launcher (`bridge.py`).
- **Presence layer** — always-on-top glow bar (color per state),
  system-tray icon with pause/resume/settings/quit menu.
- **Settings UI** — 9 tabs (General, Presence Overlay, Keybinds, Dictionaries, Voice Editing, Colors, Voice Activation, Dictation Log, Engine Console)
  persisted to `~/.clarity_v/settings.json` with
  forward-compat (unknown keys preserved) and atomic writes.
- **Engine Console** — A live, scrollable, color-coded stdout interceptor with a 2000-line ring buffer showing real-time backend prints and diagnostic logs.
- **Vocabulary Blacklist** — Custom user-defined hallucination phrase blacklist in Dictionaries settings tab to filter out unwanted Whisper hallucination loops.
- **Punctuation Comma-Consumption Fix** — Custom regex symbol-substitution logic to automatically consume surrounding commas inserted by Whisper around spoken symbols.
- **Prompt-Prefix Hallucination Filter** — Deduplicates or discards transcriptions that match or are prefixes of Whisper's initial prompt.
- **Modeless Settings Window** — Settings dialog now runs modelessly (`show()` instead of `exec()`), allowing you to position the floating start/stop button or test settings live without blocking the desktop event loop.
- **Top-Aligned Button Text** — Realigned the button status text (e.g., `START`, `STOP`, `WORKING`) to render at the top of the button above the flat logo surface when enabled, keeping the V centered.
- **Direct Log Directory Access** — Added an "Open Log Folder" button in the dictation log tab's persistent sticky footer, launching Windows Explorer at the log location.
- **Sidebar Tab Reordering** — Reordered the settings sidebar tabs to a more logical flow: General, Presence Overlay, Keybinds, Dictionaries, Voice Editing, Colors, Voice Activation, Dictation Log, Engine Console.
- **Standalone Windows Executable** — Fully packaged the application into a standalone build (`dist/clarity-v/clarity-v.exe`) with the custom `cv_logo.ico` set as the application icon.
- **Settings UI Polish**: Cleaned up the Voice Engine labels (renamed to "Detection Threshold", "End by Silence", etc.) and added intuitive hover tooltips. Replaced raw number spinboxes with dragging sliders, and added a live visual threshold marker for the noise gate.
- **Interactive Dictionary Editor** — The settings UI now has a dedicated "Dictionary" tab with a fully interactive data table. You can add, edit, and remove word substitutions directly in the UI without touching the JSON files.
- **Audio Capture Overhaul** — Migrated from `pyaudio` to `sounddevice` for continuous, non-blocking asynchronous audio streaming and live level metering.
- **Floating Button Threading Fix** — Transcription is now properly offloaded to a background thread when triggered via the floating start/stop button, preventing the Qt UI from freezing during generation.
- **Cross-platform adapter layer** — `src/clarity_v/platform/_base.py`
  defines the OS interface; `windows.py` is the v1.0 reference
  implementation. Linux/macOS/Wayland adapters are planned (see README)
  but not yet on disk; contributing one means adding a single file behind
  the same interface.
- **AI-readable training guide** — `TRAINING.md` written so an AI agent
  can walk a Person through training their own wake word.
- **Documentation** — README, ARCHITECTURE (state machine deep dive),
  PRIVACY (data flow), CONTRIBUTING (platform adapter guide),
  BUILD_PLAN (verification discipline), TRAINING.

### Not yet shipped

- True mid-dictation key commands (`delete that` → Ctrl+Z, etc.) — v1.x
  via periodic micro-transcribes. Mid-dictation insertions (`new
  paragraph` → `\n\n`) work today via the dictionary.
- macOS adapter (planned v1.2 — needs Apple Developer ID for notarization).
- Linux X11 adapter (planned v1.1 — small swap from Windows reference).
- Linux Wayland adapter (planned v1.3 — portal-based key injection).
- U.Plane integration hook (the paid path).
