"""
Settings persistence tests — pure data, no Qt dependency.

Covers: defaults, round-trip save/load, forward-compat (unknown keys
preserved), backward-compat (missing keys default), wake_word entries,
malformed JSON handling.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


from clarity_v.settings.model import Settings, WakeWordEntry


class TestDefaults:
    def test_construct(self):
        s = Settings()
        assert s.language_lock == ""
        assert s.whisper_initial_prompt == ""
        assert s.vocabulary_blacklist == ""
        assert s.telemetry_enabled is False
        assert s.silence_rms_threshold == 0.005
        # Default 0.0 = AI never autonomously ends a recording or opens
        # an auto post-paste window. The Person decides. (Forkers can
        # set positive values to opt back into those behaviors.)
        assert s.silence_seconds_to_stop == 0.0
        assert s.commit_window_seconds == 0.0
        assert s.min_recording_seconds == 0.0
        assert s.show_glow_bar is True
        assert s.show_tray_icon is True
        assert s.profiles_enabled is True
        assert s.in_dictation_commands_enabled is True
        assert s.wake_words_enabled is True
        # Defaults ship with the two trained wake models: cv_go (start)
        # + cv_over (stop). cv_go fires with conservative threshold;
        # cv_over fires lower because missed catches are worse than
        # false positives for the stop signal.
        assert len(s.wake_words) == 2
        names = {w.name for w in s.wake_words}
        assert names == {"cv_go", "cv_over"}
        cv_go = next(w for w in s.wake_words if w.name == "cv_go")
        cv_over = next(w for w in s.wake_words if w.name == "cv_over")
        assert cv_go.role == "start"
        assert cv_over.role == "stop"
        assert cv_go.threshold == 0.5
        assert cv_over.threshold == 0.35


class TestRoundTrip:
    def test_save_load(self, tmp_path):
        p = tmp_path / "settings.json"
        s = Settings()
        s.language_lock = "pt"
        s.whisper_initial_prompt = "Custom bilingual prompt."
        s.vocabulary_blacklist = "phrase1, phrase2"
        s.commit_window_seconds = 8.0
        s.profiles_enabled = False
        s.in_dictation_commands_enabled = False
        s.wake_words_enabled = False
        s.wake_words = [
            WakeWordEntry(
                name="hey_clarity",
                model_path="models/wake_words/hey_clarity.onnx",
                threshold=0.6,
            ),
        ]
        s.save(p)

        loaded = Settings.load(p)
        assert loaded.language_lock == "pt"
        assert loaded.whisper_initial_prompt == "Custom bilingual prompt."
        assert loaded.vocabulary_blacklist == "phrase1, phrase2"
        assert loaded.commit_window_seconds == 8.0
        assert loaded.profiles_enabled is False
        assert loaded.in_dictation_commands_enabled is False
        assert loaded.wake_words_enabled is False
        assert len(loaded.wake_words) == 1
        assert loaded.wake_words[0].name == "hey_clarity"
        assert loaded.wake_words[0].threshold == 0.6
        assert loaded.wake_words[0].model_path == "models/wake_words/hey_clarity.onnx"

    def test_default_when_missing_file(self, tmp_path):
        p = tmp_path / "does_not_exist.json"
        s = Settings.load(p)
        # Loading a missing file returns defaults without creating the file.
        assert s.language_lock == ""
        assert not p.exists()

    def test_save_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "nested" / "deeper" / "settings.json"
        s = Settings()
        s.save(p)
        assert p.exists()


class TestForwardCompat:
    """Unknown keys (newer version's fields) survive a round-trip."""

    def test_unknown_keys_preserved(self, tmp_path):
        p = tmp_path / "settings.json"
        # Write a file with a key our model doesn't know.
        p.write_text(
            json.dumps(
                {
                    "language_lock": "en",
                    "future_setting_we_dont_know": "hello",
                    "another_unknown": 42,
                }
            )
        )
        # Loading drops the unknowns (they're not our fields).
        s = Settings.load(p)
        assert s.language_lock == "en"

        # But saving preserves them in the file.
        s.save(p)
        raw = json.loads(p.read_text())
        assert raw["future_setting_we_dont_know"] == "hello"
        assert raw["another_unknown"] == 42
        # And our updated field is there too.
        assert raw["language_lock"] == "en"


class TestBackwardCompat:
    """Missing keys (older version's settings file) fall back to defaults."""

    def test_partial_file(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text(json.dumps({"language_lock": "pt"}))
        s = Settings.load(p)
        assert s.language_lock == "pt"
        # Other fields fall back to defaults (commit_window_seconds = 0.0
        # because the engine doesn't auto-open a post-paste window unless
        # the Person opts in).
        assert s.commit_window_seconds == 0.0
        assert s.show_glow_bar is True

    def test_empty_file(self, tmp_path):
        p = tmp_path / "settings.json"
        p.write_text("{}")
        s = Settings.load(p)
        # Everything defaults.
        assert s.language_lock == ""


class TestMalformedJSON:
    def test_invalid_json_returns_defaults(self, tmp_path, capsys):
        p = tmp_path / "settings.json"
        p.write_text("{not valid json")
        s = Settings.load(p)
        assert s.language_lock == ""
        captured = capsys.readouterr()
        assert "[Settings]" in captured.out


class TestWakeWordEntry:
    def test_default(self):
        w = WakeWordEntry(name="hey_jarvis")
        assert w.name == "hey_jarvis"
        assert w.model_path is None
        assert w.threshold == 0.5

    def test_full(self):
        w = WakeWordEntry(name="hey_clarity", model_path="x.onnx", threshold=0.6)
        assert w.threshold == 0.6
        assert w.model_path == "x.onnx"


class TestAtomicSave:
    def test_save_atomic_no_corrupt_on_partial(self, tmp_path):
        """The save uses write-then-rename so a crash mid-save doesn't
        leave the file in a partial state."""
        p = tmp_path / "settings.json"
        s = Settings()
        s.save(p)
        # First save succeeded; file is valid JSON.
        json.loads(p.read_text())

        # Save again — should still succeed and not leave .tmp behind.
        s.language_lock = "en"
        s.save(p)
        assert not (tmp_path / "settings.json.tmp").exists()
        assert json.loads(p.read_text())["language_lock"] == "en"


class TestWakeWordsTabRoundTrip:
    """The Wake Words settings tab renders each entry as one text line
    and parses it back when the Person hits Save. Every field of the
    entry — including ``role`` — must survive that cycle. Otherwise
    cv_over.role=stop silently degrades to role=start on save, which
    breaks the stop-wake architecture entirely.

    These tests target the parser/formatter helpers directly so they
    run without needing Qt up.
    """

    def test_format_full_entry(self):
        from clarity_v.settings.window import _format_wake_word_entry

        w = WakeWordEntry(
            name="cv_over",
            model_path="models/wake_words/cv_over.onnx",
            threshold=0.483,
            role="stop",
        )
        assert _format_wake_word_entry(w) == (
            "name=cv_over model_path=models/wake_words/cv_over.onnx "
            "threshold=0.483 role=stop"
        )

    def test_format_without_model_path(self):
        from clarity_v.settings.window import _format_wake_word_entry

        w = WakeWordEntry(name="hey_jarvis", threshold=0.5, role="start")
        assert _format_wake_word_entry(w) == (
            "name=hey_jarvis threshold=0.5 role=start"
        )

    def test_parse_full_entry(self):
        from clarity_v.settings.window import _parse_wake_word_entry

        entry = _parse_wake_word_entry(
            "name=cv_over model_path=x.onnx threshold=0.483 role=stop"
        )
        assert entry is not None
        assert entry.name == "cv_over"
        assert entry.model_path == "x.onnx"
        assert entry.threshold == 0.483
        assert entry.role == "stop"

    def test_parse_blank_returns_none(self):
        from clarity_v.settings.window import _parse_wake_word_entry

        assert _parse_wake_word_entry("") is None
        assert _parse_wake_word_entry("   ") is None

    def test_parse_comment_returns_none(self):
        from clarity_v.settings.window import _parse_wake_word_entry

        assert _parse_wake_word_entry("# this is a comment") is None

    def test_parse_no_name_returns_none(self):
        from clarity_v.settings.window import _parse_wake_word_entry

        assert _parse_wake_word_entry("threshold=0.5 role=start") is None

    def test_parse_missing_role_defaults_to_start(self):
        """Backward-compat: a line without role= falls back to start,
        matching WakeWordEntry's dataclass default."""
        from clarity_v.settings.window import _parse_wake_word_entry

        entry = _parse_wake_word_entry("name=foo threshold=0.5")
        assert entry is not None
        assert entry.role == "start"

    def test_parse_bad_threshold_falls_back_to_default(self):
        from clarity_v.settings.window import _parse_wake_word_entry

        entry = _parse_wake_word_entry("name=foo threshold=garbage role=start")
        assert entry is not None
        assert entry.threshold == 0.5

    def test_parse_unknown_tokens_tolerated(self):
        """Future fields don't break older parsers — unknown tokens drop."""
        from clarity_v.settings.window import _parse_wake_word_entry

        entry = _parse_wake_word_entry(
            "name=foo threshold=0.5 role=stop future_field=hello"
        )
        assert entry is not None
        assert entry.name == "foo"
        assert entry.role == "stop"

    def test_round_trip_preserves_role_for_default_settings(self):
        """The original defect: cv_over.role=stop must survive a full
        serialize+parse cycle. With the pre-fix code this test was red —
        role got dropped silently because the parser never read role=
        and the formatter never wrote it."""
        from clarity_v.settings.window import (
            _format_wake_word_entry,
            _parse_wake_word_entry,
        )

        defaults = Settings()
        # Sanity: defaults ship both wake roles, otherwise this test
        # isn't exercising what it thinks.
        roles = {w.name: w.role for w in defaults.wake_words}
        assert roles == {"cv_go": "start", "cv_over": "stop"}

        for original in defaults.wake_words:
            line = _format_wake_word_entry(original)
            parsed = _parse_wake_word_entry(line)
            assert parsed is not None
            assert parsed.name == original.name
            assert parsed.model_path == original.model_path
            assert parsed.threshold == original.threshold
            assert parsed.role == original.role, (
                f"role lost for {original.name}: "
                f"was {original.role!r}, now {parsed.role!r}"
            )
