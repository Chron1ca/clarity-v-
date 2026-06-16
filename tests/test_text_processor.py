"""
Unit tests for text_processor.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clarity_v.text_processor import process_text_transforms, clean_punctuation_and_spaces


class TestPunctuationCleanup:
    def test_collapse_spaces(self):
        assert clean_punctuation_and_spaces("hello    world") == "hello world"
        assert clean_punctuation_and_spaces("  hello world  ") == "hello world"

    def test_collapse_commas(self):
        assert clean_punctuation_and_spaces("hello, , world") == "hello, world"
        assert clean_punctuation_and_spaces("hello,, world") == "hello, world"
        assert clean_punctuation_and_spaces("hello,  , world") == "hello, world"

    def test_comma_near_periods(self):
        assert clean_punctuation_and_spaces("hello, . world") == "hello. world"
        assert clean_punctuation_and_spaces("hello, ? world") == "hello? world"
        assert clean_punctuation_and_spaces("hello! , world") == "hello! world"

    def test_space_before_punctuation(self):
        assert clean_punctuation_and_spaces("hello , world") == "hello, world"
        assert clean_punctuation_and_spaces("hello .") == "hello."
        assert clean_punctuation_and_spaces("hello ?") == "hello?"

    def test_newline_boundary(self):
        # Leading commas on newlines should be stripped
        assert clean_punctuation_and_spaces("hello,\n, world") == "hello,\nworld"
        assert clean_punctuation_and_spaces("hello\n, world") == "hello\nworld"
        assert clean_punctuation_and_spaces("hello\n   world") == "hello\nworld"


class TestTextTransforms:
    VOICE_COMMANDS = {
        "caps on": {"phase": "during", "action": "transform", "type": "caps_on"},
        "caps off": {"phase": "during", "action": "transform", "type": "caps_off"},
        "all caps on": {"phase": "during", "action": "transform", "type": "caps_on"},
        "all caps off": {"phase": "during", "action": "transform", "type": "caps_off"},
        "cap next": {"phase": "during", "action": "transform", "type": "cap_next"},
        "capitalize next word": {"phase": "during", "action": "transform", "type": "cap_next"},
        "bold on": {"phase": "during", "action": "transform", "type": "bold_on"},
        "bold off": {"phase": "during", "action": "transform", "type": "bold_off"},
        "italic on": {"phase": "during", "action": "transform", "type": "italic_on"},
        "italic off": {"phase": "during", "action": "transform", "type": "italic_off"},
        "code on": {"phase": "during", "action": "transform", "type": "code_on"},
        "code off": {"phase": "during", "action": "transform", "type": "code_off"},
        "new line": {"phase": "during", "action": "transform", "type": "new_line"},
        "new paragraph": {"phase": "during", "action": "transform", "type": "new_paragraph"},
    }

    def test_casing_modes(self):
        text = "hello caps on world caps off back to normal"
        assert process_text_transforms(text, self.VOICE_COMMANDS) == "hello WORLD back to normal"

    def test_cap_next(self):
        text = "hello cap next world back to normal"
        assert process_text_transforms(text, self.VOICE_COMMANDS) == "hello World back to normal"
        
        # Test punctuation skip
        text = "hello cap next, world"
        assert process_text_transforms(text, self.VOICE_COMMANDS) == "hello, World"

    def test_markdown_styling(self):
        text = "hello bold on world bold off back to normal"
        assert process_text_transforms(text, self.VOICE_COMMANDS) == "hello **world** back to normal"

        text = "hello italic on world italic off"
        assert process_text_transforms(text, self.VOICE_COMMANDS) == "hello _world_"

        text = "hello code on world code off"
        assert process_text_transforms(text, self.VOICE_COMMANDS) == "hello `world`"

    def test_newlines(self):
        text = "hello new line world"
        assert process_text_transforms(text, self.VOICE_COMMANDS) == "hello\nworld"

        text = "hello, new line, world"
        assert process_text_transforms(text, self.VOICE_COMMANDS) == "hello,\nworld"

        text = "hello new paragraph world"
        assert process_text_transforms(text, self.VOICE_COMMANDS) == "hello\n\nworld"

    def test_spacing_robustness(self):
        # Multiple spaces inside the trigger should still match
        text = "hello all  caps   on world all caps off normal"
        assert process_text_transforms(text, self.VOICE_COMMANDS) == "hello WORLD normal"

    def test_deferred_substitutions(self):
        # Test that substitutions run before casing transform so casing matches expanded text
        def mock_subs(t):
            return t.replace("open paren", "(").replace("close paren", ")")

        text = "hello cap next open paren world close paren"
        res = process_text_transforms(text, self.VOICE_COMMANDS, apply_substitutions_fn=mock_subs)
        assert res == "hello (World)"
