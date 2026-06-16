# Contributing to Clarity.V

Clarity.V is built to be **used, shared, and forked**. Use it as your daily driver. Share it with anyone who wants free local dictation. Fork it when you want it to do something it doesn't do yet, or work somewhere it doesn't work yet.

This document is the contributor's map: where the codebase respects your time, where the swap points are, and what a useful PR looks like.

If you're here to add Mac/Linux/Wayland support, scroll to [Add a platform](#add-a-platform). If you're here to swap Whisper for another STT engine or OpenWakeWord for another wake-word library, scroll to [Add a backend](#add-a-backend).

---

## Philosophy

- **Forks are the metric.** A clean adapter interface is an invitation. If you can write one file behind a narrow interface and have a working build for your OS or your favorite library, that's a successful project. Stars are casual; forks are commitment.
- **The interface IS the contributor doc.** Read the `_base.py` file in the relevant directory. That tells you everything you need to implement. You should not need to understand the rest of the codebase.
- **Completion is the only metric.** PRs that say "should work" without a verification command and captured output get rejected. PRs that say "verified with this output: ..." get merged.
- **No clever rewrites.** Match the existing style. Match the existing patterns. If you think the existing pattern is wrong, open an issue first.

---

## Repo layout

```text
clarity-v/
â”œâ”€â”€ README.md                   the pitch
â”œâ”€â”€ ARCHITECTURE.md             state machine deep dive
â”œâ”€â”€ PRIVACY.md                  what leaves your machine (nothing)
â”œâ”€â”€ CONTRIBUTING.md             you are here
â”œâ”€â”€ BUILD_PLAN.md               phase-by-phase build plan with verification gates
â”œâ”€â”€ CHANGELOG.md                versioned change history
â”œâ”€â”€ TRAINING.md                 train your own wake word, end-to-end
â”œâ”€â”€ LICENSE                     MIT
â”œâ”€â”€ pyproject.toml              ruff + pytest config (line-length 88)
â”œâ”€â”€ requirements.txt            runtime Python dependencies
â”œâ”€â”€ run.pyw                     entry point (windowed; no console)
â”œâ”€â”€ wake_config.json            runtime wake-word config
â”œâ”€â”€ src/clarity_v/
│   ├── __init__.py
│   ├── app.py                  ← wires engine + presence + settings + platform
│   ├── dictation.py            ← state-machine orchestrator
│   ├── whisper_engine.py       ← faster-whisper wrapper; language=None default
│   ├── audio.py                ← sounddevice capture
│   ├── wake.py                 ← OpenWakeWord wrapper, role-routed (start/stop)
│   ├── dictionary.py           ← JSON loader, extends chain, hot reload
│   ├── filters.py              ← pure functions; no deps beyond stdlib + re
│   ├── commit.py               ← post-paste Whisper-transcribe + voice command match
│   ├── buffer.py               ← LastDictationBuffer (separate from OS clipboard)
│   ├── dictation_log.py        ← opt-in JSONL log with size rotation
│   ├── log_capture.py          ← thread-safe log capture utility with ring-buffer
│   ├── sounds.py               ← activation/deactivation cue playback
│   ├── state.py                ← State enum + StateManager (thread-safe broadcaster)
│   ├── presence/               ← glow bar + tray + floating start/stop button
│   ├── settings/                 ← Qt 9-tab settings dialog (General, Presence Overlay, Keybinds, Dictionaries, Voice Editing, Colors, Voice Activation, Dictation Log, Engine Console)
│   └── platform/               ← OS-specific adapters
│       ├── _base.py            ← interface; READ THIS to contribute a platform
│       ├── __init__.py         ← get_adapter() factory
│       └── windows.py          ← v1.0 reference implementation
├── tests/                      ← pytest unit tests (no mic required)
├── tools/                      ← interactive verification + training scripts
│   ├── verify_*.py             ← one per build phase
│   ├── run_voice_tests.py      ← orchestrates all phases in order
│   └── training/               ← wake-word training pipeline
├── scripts/                    ← developer helpers (dev.py)
├── models/wake_words/          ← shipped trained ONNX files
├── dictionaries/
│   ├── default.json            ← English prose + voice commands
│   └── python.json             ← Python coding dictionary (extends default)
├── packaging/                  ← PyInstaller spec for Windows builds
├── assets/sounds/              ← activation/deactivation WAV cues
└── .github/                    ← issue templates + CI workflow
```

Other platforms (`linux_x11.py`, `macos.py`, `linux_wayland.py`) are **planned, not yet on disk** â€” adding one is exactly the contribution flow described in [Add a platform](#add-a-platform) below.

---

## Check your work

One command runs everything (lint, formatting, tests) in the right order:

```bash
python scripts/dev.py check
```

This is exactly what GitHub runs on your pull request via `.github/workflows/checks.yml`. If `dev.py check` is green locally, your PR will pass CI.

If anything's off:

```bash
python scripts/dev.py fix    # auto-fix lint + apply formatting
python scripts/dev.py check  # re-verify
```

Other shortcuts: `dev.py test`, `dev.py lint`, `dev.py format`, `dev.py help`.

### Catching problems at commit time

Optional but recommended â€” install [pre-commit](https://pre-commit.com/) once:

```bash
pip install pre-commit
pre-commit install
```

After that, the same checks run automatically every time you `git commit`. If anything fails, the commit is blocked until you fix it. Saves a round-trip with CI later. Config lives in `.pre-commit-config.yaml`.

To skip just this once in an emergency: `git commit --no-verify` â€” don't make a habit.

---

## Add a platform

You want to make Clarity.V work on macOS, Linux Wayland, BSD, Haiku, your custom embedded board, or anywhere `pip install -r requirements.txt` runs.

**Steps:**

1. Read [src/clarity_v/platform/_base.py](src/clarity_v/platform/_base.py). That's the entire interface. ~70 lines, mostly comments.
2. Read [src/clarity_v/platform/windows.py](src/clarity_v/platform/windows.py) as a reference implementation.
3. Create `src/clarity_v/platform/yourplatform.py` implementing every abstract method on `PlatformAdapter`.
4. Add a branch to `get_adapter()` in `src/clarity_v/platform/__init__.py` that returns your adapter when `sys.platform` matches.
5. Test manually: launch Clarity.V, confirm wake-word fires, dictation works, glow bar appears.
6. PR with: your platform file, the factory change, and a short note on what you tested.

**The five things your platform must do:**

- `register_hotkey(combo, on_press, on_release=None, suppress=True)` â€” global keyboard shortcut listener.
- `unregister_all_hotkeys()` â€” drop everything you registered, on shutdown.
- `send_key_combo(combo)` â€” synthesize a keypress like `"ctrl+enter"`.
- `paste_text(text)` â€” put text at the cursor in the focused app (clipboard + Ctrl+V is fine for most platforms).
- `play_sound(wav_path)` â€” async WAV playback for the activate/deactivate cues.
- `make_window_topmost(window_handle)` â€” keep the glow bar on top.

Edge cases the Windows adapter handles that yours might need to too:

- **Clipboard restore after paste.** The user's previous clipboard content should survive a paste-at-cursor operation.
- **Topmost re-assertion.** Some OSes let other always-on-top apps steal Z-order. Re-assert every 500 ms with a background thread if needed.
- **Modifier key release on failure.** If `send_key_combo` partially fails, release all held modifiers before raising â€” otherwise the user's keyboard gets stuck with Ctrl held.

---

## Add a backend

The platform adapter is the load-bearing fork point. Clarity.V also has narrower swap points for libraries you might prefer.

### Wake-word backend

Today Clarity.V uses [OpenWakeWord](https://github.com/dscripka/openWakeWord). Alternatives worth contributing:

- **Picovoice Porcupine** â€” higher accuracy, commercial license required.
- **Snowboy** â€” discontinued upstream but forks exist.
- **Custom model** â€” train your own with PyTorch, expose it via the same interface.

The interface is currently inline in `src/clarity_v/wake.py`. If you want to PR a swap point, the right move is:

1. Open an issue proposing the abstraction.
2. We'll factor a `wake/_base.py` interface together.
3. Then your backend becomes one file alongside the OpenWakeWord one.

### STT backend

Today Clarity.V uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (Whisper via CTranslate2). Alternatives:

- **[whisper.cpp](https://github.com/ggerganov/whisper.cpp)** â€” zero Python deps, embeddable, very fast on Apple Silicon.
- **[Vosk](https://alphacephei.com/vosk/)** â€” smaller models, offline, older but lighter.
- **[NVIDIA NeMo](https://github.com/NVIDIA/NeMo)** â€” large enterprise option.
- **Your favorite cloud STT** â€” Deepgram, AssemblyAI, etc. (Would break the no-API-key promise; would need to be opt-in.)

Same pattern: open an issue, we factor `whisper_engine.py`'s public API into an interface, your backend implements it.

### Paste backend

The clipboard+Ctrl+V strategy works on most platforms but some apps fight it. Alternatives:

- **Synthetic typing** â€” character-by-character key events. Slower but works in some hostile text fields.
- **macOS AppleScript** â€” direct app insertion via OSA.
- **Wayland's wl-clipboard + portal API** â€” Wayland-native.

---

## Code style

- Python 3.10+. Use modern type hints (`list[str]`, `dict[str, int]`, `Optional[X]` where appropriate).
- Line length 88, enforced by `ruff format` (configured in `pyproject.toml`). Run `python scripts/dev.py format` to apply. Editors that default to 79 chars (PEP 8) flag lines that are fine by project standard â€” ignore those.
- Use `from __future__ import annotations` at the top of any module that uses forward type references.
- Docstrings are documentation. Write them for any public function or class.
- Comments explain *why*, not *what*. Code says what.
- No emojis in source code unless explicitly idiomatic for the file (e.g., a CLI banner).
- Test what you build. PRs that touch logic without tests need a justification in the PR description.

---

## Test style

- pytest, no other framework.
- One file per module under test: `tests/test_<modulename>.py`.
- Use classes to group related tests; methods named `test_*`.
- Use `tmp_path` for any test that needs files on disk.
- Tests should run in under a second each unless they explicitly hit a model. Integration tests that touch Whisper or a mic go under `tools/verify_*.py`, not `tests/`.
- A failing test must produce a useful diff. Use specific assertion messages.

---

## PR checklist

Before submitting:

- [ ] `python scripts/dev.py check` is green (runs lint + format-check + tests in one go).
- [ ] If your PR adds a platform or backend, you have manually verified it works on your machine, and the PR description has the verification output.
- [ ] If your PR changes user-visible behavior, the README/ARCHITECTURE/PRIVACY docs are updated to match.
- [ ] No new dependencies unless you've explained why in the PR description.
- [ ] Your commit messages describe *what* and *why*, not just *what*.

GitHub will run the same `check` automatically on your PR â€” see `.github/workflows/checks.yml`. If it's green locally, it'll be green on GitHub.

---

## Issue templates

When opening an issue:

- **Bug** â€” what you saw, what you expected, OS + Python version, steps to reproduce.
- **Feature** â€” what problem you have, what you want Clarity.V to do, why current capabilities don't solve it.
- **Platform request** â€” "I want Clarity.V on FreeBSD" â€” link to your fork-in-progress if any, list any specific platform questions.

---

## License

MIT. Your contributions are licensed under the same MIT license. You retain copyright on your contributions; you grant Clarity.V the right to use them under MIT.

By submitting a PR you confirm you have the right to license the code you're submitting.

