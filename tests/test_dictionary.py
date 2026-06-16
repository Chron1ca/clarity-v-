"""
Dictionary tests — JSON loading, extends-chain, substitutions, macros,
voice commands, hot reload.

No mic, no model, no platform dependency. Pure data + file I/O.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from clarity_v.dictionary import Dictionary, load_default


REPO_ROOT = Path(__file__).parent.parent
DICT_DIR = REPO_ROOT / "dictionaries"


# ─── Shipped dictionary loading ────────────────────────────────────────


class TestShippedDictionaries:
    def test_default_loads(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        assert d.name == "Default"
        assert len(d.substitutions) > 0
        # Known substitution from default.json
        assert "git hub" in d.substitutions
        assert d.substitutions["git hub"] == "GitHub"

    def test_default_has_file_extensions(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        assert d.substitutions["dot py"] == ".py"
        assert d.substitutions["dot json"] == ".json"

    def test_default_has_voice_commands(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        assert "caps on" in d.voice_commands
        assert "enter" in d.voice_commands
        assert "send" in d.voice_commands
        assert d.voice_commands["enter"]["action"] == "submit"
        assert d.voice_commands["enter"]["phase"] == "after"

    def test_python_extends_default(self):
        d = Dictionary.load(DICT_DIR / "Python.json")
        # Own substitutions
        assert "deaf" in d.substitutions
        assert d.substitutions["deaf"] == "def"
        # INHERITED substitutions from default.json
        assert "git hub" in d.substitutions
        assert d.substitutions["git hub"] == "GitHub"

    def test_python_has_macros(self):
        d = Dictionary.load(DICT_DIR / "Python.json")
        assert "def func" in d.macros
        assert "def function_name" in d.macros["def func"]
        assert "try block" in d.macros
        assert "except Exception" in d.macros["try block"]

    def test_python_inherits_voice_commands(self):
        d = Dictionary.load(DICT_DIR / "Python.json")
        # python.json defines empty voice_commands; defaults must shine through.
        assert "caps on" in d.voice_commands
        assert "enter" in d.voice_commands

    def test_load_default_helper(self):
        d = load_default(DICT_DIR)
        assert d.name == "Default"


# ─── apply_substitutions ───────────────────────────────────────────────


class TestSubstitutions:
    def test_empty_text(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        assert d.apply_substitutions("") == ""

    def test_known_substitution(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        assert d.apply_substitutions("git hub is cool") == "GitHub is cool"

    def test_case_insensitive(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        assert d.apply_substitutions("GIT HUB works") == "GitHub works"

    def test_no_match_passthrough(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        assert d.apply_substitutions("nothing to swap") == "nothing to swap"

    def test_word_boundary(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        # "github" should not match inside "githubber" (word boundary required)
        result = d.apply_substitutions("githubber")
        assert result == "githubber"
        # But it should match standalone
        result = d.apply_substitutions("github here")
        assert result == "GitHub here"

    def test_longer_first(self, tmp_path):
        # If both "u" and "u plane" are substitutions, "u plane" should win.
        data = {
            "name": "test",
            "description": "",
            "substitutions": {"u": "X", "u plane": "U.Plane"},
            "macros": {},
            "voice_commands": {},
        }
        p = tmp_path / "test.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        d = Dictionary.load(p)
        assert d.apply_substitutions("u plane is the OS") == "U.Plane is the OS"

    def test_symbol_comma_consumed_both_sides(self):
        """Whisper transcribes 'open quote' as ', open quote,' — commas must be eaten."""
        d = Dictionary.load(DICT_DIR / "Default.json")
        result = d.apply_substitutions("Hello, open quote, world")
        # Commas removed, space preserved between words and symbol
        assert result == 'Hello " world'

    def test_symbol_period_consumed_both_sides(self):
        """Whisper transcribes 'open quote' as '. open quote.' — periods must be eaten."""
        d = Dictionary.load(DICT_DIR / "Default.json")
        result = d.apply_substitutions("Hello. open quote. world")
        assert result == 'Hello " world'

    def test_symbol_period_consumed_leading_only(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        result = d.apply_substitutions("Hello. open quote world")
        assert result == 'Hello " world'

    def test_symbol_period_consumed_trailing_only(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        result = d.apply_substitutions("Hello open quote. world")
        assert result == 'Hello " world'

    def test_symbol_comma_consumed_trailing_only(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        result = d.apply_substitutions("Hello open quote, world")
        assert result == 'Hello " world'

    def test_symbol_comma_consumed_leading_only(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        result = d.apply_substitutions("Hello, open quote world")
        assert result == 'Hello " world'

    def test_symbol_no_comma_still_works(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        result = d.apply_substitutions("Hello open quote world")
        assert result == 'Hello " world'

    def test_symbol_multiple_in_sentence(self):
        """Multiple symbols with commas in one sentence."""
        d = Dictionary.load(DICT_DIR / "Default.json")
        result = d.apply_substitutions("say, open quote, hello, close quote, done")
        assert result == 'say " hello " done'

    def test_word_substitution_preserves_commas(self):
        """Normal word substitutions must NOT eat commas — only symbols do."""
        d = Dictionary.load(DICT_DIR / "Default.json")
        result = d.apply_substitutions("I use, git hub, for code")
        assert result == "I use, GitHub, for code"


# ─── expand_macros ─────────────────────────────────────────────────────


class TestMacros:
    def test_empty_text(self):
        d = Dictionary.load(DICT_DIR / "Python.json")
        assert d.expand_macros("") == ""

    def test_no_macros_loaded(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        # default.json has no macros, only _comment
        assert d.expand_macros("anything") == "anything"

    def test_macro_expansion(self):
        d = Dictionary.load(DICT_DIR / "Python.json")
        result = d.expand_macros("def func")
        assert "def function_name(args):" in result
        assert "pass" in result

    def test_macro_in_context(self):
        d = Dictionary.load(DICT_DIR / "Python.json")
        result = d.expand_macros("here is def func inline")
        # The macro expanded; surrounding text preserved
        assert "def function_name(args):" in result
        assert "here is" in result
        assert "inline" in result

    def test_multiline_template_has_real_newlines(self):
        d = Dictionary.load(DICT_DIR / "Python.json")
        result = d.expand_macros("try block")
        assert "\n" in result, "Macro should contain real newlines"
        assert "try:" in result
        assert "except" in result

    def test_case_insensitive(self):
        d = Dictionary.load(DICT_DIR / "Python.json")
        result = d.expand_macros("DEF FUNC")
        assert "def function_name" in result


# ─── match_voice_command ───────────────────────────────────────────────


class TestVoiceCommands:
    def test_empty_text(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        assert d.match_voice_command("", "after") is None

    def test_enter_in_after_phase(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        cmd = d.match_voice_command("enter", "after")
        assert cmd is not None
        assert cmd["action"] == "submit"

    def test_enter_in_wrong_phase(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        # "enter" is phase=after; asking for "during" must return None.
        assert d.match_voice_command("enter", "during") is None

    def test_caps_on_in_during_phase(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        cmd = d.match_voice_command("caps on", "during")
        assert cmd is not None
        assert cmd["action"] == "transform"
        assert cmd["type"] == "caps_on"

    def test_no_match(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        assert d.match_voice_command("xyzzy banana", "after") is None

    def test_match_with_punctuation(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        # Transcription comes through with punctuation. Should still match.
        cmd = d.match_voice_command("enter.", "after")
        assert cmd is not None
        assert cmd["action"] == "submit"

    def test_match_case_insensitive(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        cmd = d.match_voice_command("SEND", "after")
        assert cmd is not None
        assert cmd["action"] == "submit"

    def test_bold_on(self):
        d = Dictionary.load(DICT_DIR / "Default.json")
        cmd = d.match_voice_command("bold on", "during")
        assert cmd is not None
        assert cmd["action"] == "transform"
        assert cmd["type"] == "bold_on"


# ─── extends chain ─────────────────────────────────────────────────────


class TestExtendsChain:
    def test_circular_detected(self, tmp_path):
        # a.json extends b, b.json extends a → circular
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        a.write_text(
            json.dumps(
                {
                    "name": "a",
                    "extends": "b",
                    "substitutions": {},
                    "macros": {},
                    "voice_commands": {},
                }
            )
        )
        b.write_text(
            json.dumps(
                {
                    "name": "b",
                    "extends": "a",
                    "substitutions": {},
                    "macros": {},
                    "voice_commands": {},
                }
            )
        )
        with pytest.raises(ValueError, match="Circular"):
            Dictionary.load(a)

    def test_missing_parent_raises(self, tmp_path):
        child = tmp_path / "child.json"
        child.write_text(
            json.dumps(
                {
                    "name": "child",
                    "extends": "nonexistent",
                    "substitutions": {},
                    "macros": {},
                    "voice_commands": {},
                }
            )
        )
        with pytest.raises(FileNotFoundError):
            Dictionary.load(child)

    def test_child_overrides_parent(self, tmp_path):
        parent = tmp_path / "parent.json"
        child = tmp_path / "child.json"
        parent.write_text(
            json.dumps(
                {
                    "name": "parent",
                    "substitutions": {"foo": "from-parent"},
                    "macros": {},
                    "voice_commands": {},
                }
            )
        )
        child.write_text(
            json.dumps(
                {
                    "name": "child",
                    "extends": "parent",
                    "substitutions": {"foo": "from-child"},
                    "macros": {},
                    "voice_commands": {},
                }
            )
        )
        d = Dictionary.load(child)
        assert d.substitutions["foo"] == "from-child"


# ─── Hot reload ────────────────────────────────────────────────────────


class TestHotReload:
    def test_reload_picks_up_new_substitution(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text(
            json.dumps(
                {
                    "name": "test",
                    "description": "",
                    "substitutions": {"old": "X"},
                    "macros": {},
                    "voice_commands": {},
                }
            )
        )
        d = Dictionary.load(p)
        assert "old" in d.substitutions
        assert "new" not in d.substitutions

        # Modify the file with a fresh substitution.
        time.sleep(0.05)  # ensure mtime changes
        p.write_text(
            json.dumps(
                {
                    "name": "test",
                    "description": "",
                    "substitutions": {"old": "X", "new": "Y"},
                    "macros": {},
                    "voice_commands": {},
                }
            )
        )

        d.start_watching(poll_interval_seconds=0.1)
        # Force a watch cycle to pick up the change.
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if "new" in d.substitutions:
                break
            time.sleep(0.05)
        d.stop_watching()

        assert "new" in d.substitutions
        assert d.substitutions["new"] == "Y"

    def test_reload_callback_fires(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text(
            json.dumps(
                {
                    "name": "test",
                    "description": "",
                    "substitutions": {},
                    "macros": {},
                    "voice_commands": {},
                }
            )
        )
        d = Dictionary.load(p)

        fired = []
        d.on_reload(lambda dct: fired.append(dct.name))

        d.start_watching(poll_interval_seconds=0.1)
        time.sleep(0.05)
        p.write_text(
            json.dumps(
                {
                    "name": "test-renamed",
                    "description": "",
                    "substitutions": {},
                    "macros": {},
                    "voice_commands": {},
                }
            )
        )
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if fired:
                break
            time.sleep(0.05)
        d.stop_watching()

        assert fired == ["test-renamed"]

    def test_bad_json_does_not_crash(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text(
            json.dumps(
                {
                    "name": "test",
                    "description": "",
                    "substitutions": {"valid": "OK"},
                    "macros": {},
                    "voice_commands": {},
                }
            )
        )
        d = Dictionary.load(p)
        assert d.substitutions == {"valid": "OK"}

        d.start_watching(poll_interval_seconds=0.1)
        time.sleep(0.05)
        # Write invalid JSON.
        p.write_text("{not valid json")
        time.sleep(0.3)  # let the watcher try to reload
        d.stop_watching()

        # Previous state is intact; the bad JSON was rejected, not applied.
        assert d.substitutions == {"valid": "OK"}
