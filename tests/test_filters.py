"""
Filters — pure function tests. No mic, no model, no platform dependency.

Each test asserts an input/output contract. If a filter regresses, these
tests catch it before any voice-flow regression test does.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make src/ importable without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


from clarity_v.filters import (
    HALLUCINATIONS,
    apply_full_pipeline,
    strip_known_hallucinations,
    strip_repeated_sentences,
    strip_wake_phrase,
)


# ─── strip_repeated_sentences ──────────────────────────────────────────


class TestRepeatedSentences:
    def test_empty(self):
        assert strip_repeated_sentences("") == ""

    def test_none_repeated(self):
        assert strip_repeated_sentences("Hello world.") == "Hello world."

    def test_two_distinct_sentences(self):
        assert strip_repeated_sentences("Hello. World.") == "Hello. World."

    def test_collapse_three_identical(self):
        assert strip_repeated_sentences("Hello. Hello. Hello.") == "Hello."

    def test_mid_strip(self):
        assert strip_repeated_sentences("First. Second. First.") == "First. Second."

    def test_case_insensitive(self):
        assert strip_repeated_sentences("Hello. hello. HELLO.") == "Hello."

    def test_punctuation_insensitive(self):
        assert strip_repeated_sentences("Hello! Hello? Hello.") == "Hello!"

    def test_question_mark_split(self):
        assert strip_repeated_sentences("How are you? How are you?") == "How are you?"

    def test_paragraph_break(self):
        result = strip_repeated_sentences("First line.\n\nSecond.\n\nFirst line.")
        assert result == "First line. Second."

    def test_whitespace_normalized_in_comparison(self):
        assert strip_repeated_sentences("Hello world. Hello  world.") == "Hello world."


# ─── strip_known_hallucinations ────────────────────────────────────────


class TestKnownHallucinations:
    def test_empty(self):
        assert strip_known_hallucinations("") == ""

    def test_clean_text_passthrough(self):
        assert (
            strip_known_hallucinations("This is real content.")
            == "This is real content."
        )

    def test_full_match_thank_you(self):
        assert strip_known_hallucinations("Thank you.") == ""

    def test_full_match_subscribe(self):
        assert strip_known_hallucinations("please subscribe") == ""

    def test_trailing_strip(self):
        result = strip_known_hallucinations("Real content here. Thanks for watching.")
        assert result == "Real content here."

    def test_trailing_strip_preserves_real(self):
        result = strip_known_hallucinations("Important info. Please subscribe.")
        assert result == "Important info."

    def test_portuguese_full_match(self):
        assert strip_known_hallucinations("Obrigado.") == ""

    def test_portuguese_trailing_strip(self):
        result = strip_known_hallucinations("Conteúdo real. Obrigado por assistir.")
        assert result == "Conteúdo real."

    def test_extra_phrases(self):
        result = strip_known_hallucinations(
            "My custom phantom", extra_phrases=["custom phantom"]
        )
        assert result == "My"


# ─── strip_wake_phrase ─────────────────────────────────────────────────


class TestWakePhraseStrip:
    def test_empty(self):
        assert strip_wake_phrase("", ["clarity-v"]) == ""

    def test_no_wake_in_text(self):
        assert strip_wake_phrase("hello world", ["clarity-v"]) == "hello world"

    def test_wake_at_start(self):
        assert (
            strip_wake_phrase("clarity-v start a recording", ["clarity-v"])
            == "start a recording"
        )

    def test_wake_at_end(self):
        assert (
            strip_wake_phrase("send this message clarity-v", ["clarity-v"])
            == "send this message"
        )

    def test_multiple_wake_phrases(self):
        result = strip_wake_phrase("clarity-v hello clarity-v world", ["clarity-v"])
        assert result == "hello world"

    def test_case_insensitive(self):
        assert strip_wake_phrase("WAKEWORD hello", ["wakeword"]) == "hello"

    def test_with_punctuation(self):
        assert strip_wake_phrase("wakeword, hello", ["wakeword"]) == "hello"

    def test_substring_not_matched(self):
        # leading word boundary required: "test" doesn't strip from "contest"
        assert strip_wake_phrase("contest needed", ["test"]) == "contest needed"


# ─── apply_full_pipeline ───────────────────────────────────────────────


class TestFullPipeline:
    def test_clean_passthrough(self):
        assert apply_full_pipeline("This is real text.") == "This is real text."

    def test_repeat_then_hallucination(self):
        # Whisper output: looped subscribe-prompts.
        result = apply_full_pipeline("Thank you for watching. Thank you for watching.")
        assert result == ""

    def test_real_text_then_trailing_hallucination(self):
        result = apply_full_pipeline("Real content. Thank you for watching.")
        assert result == "Real content."

    def test_wake_plus_content_plus_hallucination(self):
        result = apply_full_pipeline(
            "clarity-v hello world. Thanks for watching.",
            wake_phrases=["clarity-v"],
        )
        assert result == "hello world."


# ─── Prompt Hallucination Filters ──────────────────────────────────────


class TestPromptHallucinationFilters:
    def test_strip_prompt_prefix_exact(self):
        prompt = "Hello, how are you? Olá, como estás? I'm not a fake, e nem sou feio."
        # Exact prefix match
        text = "Hello, how are you? Olá, como estás?"
        assert apply_full_pipeline(text, initial_prompt=prompt) == ""

    def test_strip_prompt_prefix_with_garbage(self):
        prompt = "Hello, how are you? Olá, como estás? I'm not a fake, e nem sou feio, mas já estou late for my date. De vez em quando pinto aguarelas."
        # Prefix with trailing symbol (like feminine indicator ª or punctuation)
        text = "Hello, how are you? Olá, como estás? ª"
        assert apply_full_pipeline(text, initial_prompt=prompt) == ""
        
        # Another prefix with punctuation
        text2 = "Hello, how are you? Olá, como estás? ^^"
        assert apply_full_pipeline(text2, initial_prompt=prompt) == ""

    def test_strip_prompt_clause_at_end(self):
        prompt = "Hello, how are you? Olá, como estás? I'm not a fake."
        # Real text followed by a clause of the prompt
        text = "This is a real message. Olá, como estás?"
        assert apply_full_pipeline(text, initial_prompt=prompt) == "This is a real message."

    def test_short_word_passthrough(self):
        prompt = "Hello, how are you? Olá, como estás? I'm not a fake."
        # Tiny words that happen to be prefixes or letters in the prompt should not be stripped
        assert apply_full_pipeline("I", initial_prompt=prompt) == "I"


# ─── HALLUCINATIONS constant sanity ────────────────────────────────────


class TestHallucinationsList:
    def test_not_empty(self):
        assert len(HALLUCINATIONS) > 5

    def test_all_lowercase(self):
        for phrase in HALLUCINATIONS:
            assert phrase == phrase.lower(), f"Non-lowercase phrase: {phrase!r}"

    def test_includes_english(self):
        assert "thank you for watching" in HALLUCINATIONS

    def test_includes_portuguese(self):
        assert any("obrigad" in p for p in HALLUCINATIONS)
