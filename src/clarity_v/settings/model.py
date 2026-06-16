"""
Persistent settings model.

Stored as a single JSON file at ~/.clarity_v/settings.json. Forward-
compatible: unknown keys in the file are silently dropped; missing
keys fall back to defaults. Updating an existing file preserves any
fields the running version doesn't know about (so users running
multiple Clarity.V versions don't lose preferences from each other).

This module has no Qt dependency — the engine can read settings
headlessly. The UI lives in window.py.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


def default_path() -> Path:
    """The canonical location for the settings file."""
    return Path.home() / ".clarity_v" / "settings.json"


@dataclass
class WakeWordEntry:
    """One configured wake word — name + optional ONNX path + threshold + role.

    Role determines what the wake event does when fired:
      "start" — begins dictation (idle → recording)
      "stop"  — ends dictation (recording → processing)
    """

    name: str
    model_path: str | None = None
    threshold: float = 0.5
    role: str = "start"


@dataclass
class Settings:
    """Everything the UI lets you change. Defaults are the v1 sane values.

    Adding a new setting:
      1. Add a field here with a default.
      2. (Optional) Add a UI control in the relevant window.py tab.
      3. Existing settings files load fine — missing keys use the default.
    """

    # ─── General ──────────────────────────────────────────────────────
    language_lock: str = ""  # "" = auto-detect; "en", "pt", etc.
    whisper_model_size: str = "medium"  # "tiny", "base", "small", "medium", "large"
    whisper_initial_prompt: str = ""
    telemetry_enabled: bool = False  # opt-in, off by default
    dictation_log_enabled: bool = True  # on by default
    sound_enabled: bool = True  # activation/deactivation chirps
    sound_volume: float = 0.5   # sound volume from 0.0 to 1.0
    sound_activate_path: str = ""  # "" = bundled default
    sound_deactivate_path: str = ""  # "" = bundled default
    sound_paste_path: str = ""  # "" = bundled default

    # ─── Voice flow ───────────────────────────────────────────────────
    # All three of the below default to 0.0 — the AI never autonomously
    # ends a recording, discards a "too short" one, or auto-opens a
    # post-paste listening window. The Person decides. Set any of them
    # to a positive number to opt into that behavior.
    silence_rms_threshold: float = 0.005  # RMS threshold for "silence"
    silence_seconds_to_stop: float = 0.0  # 0 = no auto-stop on silence
    min_recording_seconds: float = 0.0  # 0 = no "too short" discard
    commit_window_seconds: float = 0.0  # 0 = no auto post-paste window

    # ─── Wake words ───────────────────────────────────────────────────
    # Defaults: the two trained models that ship with Clarity.V.
    # cv_go starts dictation (conservative threshold 0.5).
    # cv_over ends dictation (lower threshold 0.35 — missed catches are
    # worse than false positives for the stop signal).
    wake_words: list[WakeWordEntry] = field(
        default_factory=lambda: [
            WakeWordEntry(
                name="cv_go",
                model_path="models/wake_words/cv_go.onnx",
                threshold=0.5,
                role="start",
            ),
            WakeWordEntry(
                name="cv_over",
                model_path="models/wake_words/cv_over.onnx",
                threshold=0.35,
                role="stop",
            ),
        ]
    )
    wake_cooldown_seconds: float = 0.5
    wake_words_enabled: bool = True

    # ─── Audio ────────────────────────────────────────────────────────
    audio_device_index: int | None = None  # None = system default

    # ─── Dictionary ───────────────────────────────────────────────────
    active_dictionary: str = "Default"  # which dictionary JSON to load
    dictionary_hot_reload: bool = True
    dictionary_keybinds: dict[str, str] = field(default_factory=dict)
    profiles_enabled: bool = True
    in_dictation_commands_enabled: bool = True
    vocabulary_blacklist: str = ""  # comma-separated list of words/phrases to filter out

    # ─── Presence (glow bar + start/stop button) ──────────────────────
    show_glow_bar: bool = True
    show_tray_icon: bool = True
    # 60 px gives the multi-stop gradient enough room to fade from the
    # screen edge into transparency — the bar reads as a glow, not a
    # flat colored strip. Below ~30 px the falloff has no room and the
    # bar looks like a hard-edged rectangle.
    glow_bar_height: int = 60
    # 0.75 brings the peak alpha down so idle reads as ambient rather
    # than aggressive; the multiplier scales every state proportionally.
    glow_bar_brightness: float = 0.75  # 0.0-1.0 multiplier on alpha
    glow_bar_position: str = "top"  # "top" | "bottom" | "freeform"
    glow_bar_x: int = 0  # only used when position=freeform
    glow_bar_y: int = 0  # only used when position=freeform

    # Floating start/stop button — fourth control mode (click to toggle
    # dictation; voice, PTT, and keybind are the other three). Ships
    # visible: the Person's reach surface for Pause/Settings/Quit. Win11
    # buries the tray icon in the overflow; the ball does not.
    show_start_stop_button: bool = False
    start_stop_button_locked: bool = False
    start_stop_button_size: int = 160
    start_stop_button_x: int = -1  # -1 = use bottom-right default
    start_stop_button_y: int = -1
    # Colors stored as 4-tuples [R, G, B, A] for each state.
    # Default palette: blue (standby) / green (recording) /
    # orange (transcribing) / red (error).
    color_idle: list[int] = field(
        default_factory=lambda: [51, 153, 255, 120]
    )
    color_recording: list[int] = field(
        default_factory=lambda: [51, 204, 51, 240]
    )
    color_processing: list[int] = field(
        default_factory=lambda: [255, 140, 0, 240]
    )
    color_commit_waiting: list[int] = field(
        default_factory=lambda: [100, 200, 220, 220]
    )
    color_error: list[int] = field(default_factory=lambda: [220, 30, 30, 240])

    # ─── Keybinds ─────────────────────────────────────────────────────
    keybind_ptt: str = ""  # empty = no PTT keybind
    keybind_toggle: str = "ctrl+shift+d"  # start/stop dictation toggle
    keybind_paste_last_dictation: str = "ctrl+shift+c"  # paste last transcript
    # Cancel the current dictation cycle — discards any in-flight
    # recording, skips paste, flashes the bar red briefly, returns to
    # the resting state. Default to Ctrl+Shift+Q so it never clashes
    # with common app keybinds; empty disables.
    keybind_cancel: str = "ctrl+shift+q"

    # ─── Dictation log ────────────────────────────────────────────────
    dictation_log_max_kb: int = 500  # rotate per file at this size

    # ─── U.Plane integration (optional, off by default) ───────────────
    uplane_integration_enabled: bool = False
    uplane_url: str = "http://127.0.0.1:8001"

    # ─── Load/save ────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        """Load from JSON, returning defaults for any missing fields.

        Missing file → returns defaults, does NOT create the file.
        Bad JSON → returns defaults, prints a warning.
        """
        p = path or default_path()
        if not p.exists():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[Settings] Could not parse {p}: {e}. Using defaults.")
            return cls()

        # Convert known fields; ignore unknown ones.
        known = {f.name for f in fields(cls)}
        kwargs: dict[str, Any] = {}
        for k, v in raw.items():
            if k not in known:
                continue
            if k == "wake_words" and isinstance(v, list):
                kwargs[k] = [
                    WakeWordEntry(**w) if isinstance(w, dict) else w for w in v
                ]
            else:
                kwargs[k] = v
        return cls(**kwargs)

    def save(self, path: Path | None = None) -> None:
        """Atomically write to JSON. Preserves unknown keys from the
        existing file (forward-compat with other Clarity.V versions)."""
        p = path or default_path()
        p.parent.mkdir(parents=True, exist_ok=True)

        existing: dict[str, Any] = {}
        if p.exists():
            try:
                existing = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}

        # Merge: our fields overwrite, unknown fields preserved.
        our_dict = asdict(self)
        existing.update(our_dict)

        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(p)
