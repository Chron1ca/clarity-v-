"""
Hallucination filters for Whisper output.

Whisper, like all transformer STT models, hallucinates on silence and
noise. It emits the most frequent text in its training data — YouTube
subscribe-prompts in English, equivalent phrases in Portuguese, etc. —
when the audio doesn't contain real speech.

Three layers of defense, applied in order:

  1. strip_repeated_sentences  — same sentence 2+ times = noise loop
  2. strip_known_hallucinations — known blacklist (full + trailing)
  3. strip_wake_phrase          — wake word leaked, regex it out

Each function is a pure transformation. They always return a string
(possibly empty) and never raise.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Known hallucination phrases — these are what Whisper emits when fed silence
# or noise. Lowercased; matching is case-insensitive.
HALLUCINATIONS: list[str] = [
    # English (YouTube training data is the dominant source)
    "thanks for watching",
    "thank you for watching",
    "please subscribe",
    "like and subscribe",
    "bye bye",
    "see you next time",
    "thank you for listening",
    "thank you",
    "hello, how are you? i'm doing well. let me tell you about this",
    # Portuguese — same training-data effect
    "obrigado por assistir",
    "obrigado por verem",
    "obrigada por assistir",
    "obrigado",
    "obrigada",
    "se gostaste deste vídeo",
    "subscreva o canal",
    "até a próxima",
    "tchau",
    "olá, como estás? estou bem. vamos falar sobre isto",
    "olá, como estás? estou bem",
    "olá, como estás",
    "estou bem",
    "vamos falar sobre isto",
    # Spanish — bonus coverage
    "gracias por ver",
    "suscríbete",
    # French
    "merci d'avoir regardé",
    # German
    "danke fürs zuschauen",
]


def strip_repeated_sentences(text: str) -> str:
    """Drop duplicate sentences after the first occurrence.

    Whisper's silence-hallucination pattern is the same sentence repeated 2+
    times in one transcription. First occurrence is kept (might be real text);
    subsequent matches are dropped.

    Detection is case-insensitive and normalizes punctuation/whitespace before
    comparison, so "Hello." and "hello," count as the same sentence.

    Args:
        text: raw transcription string.

    Returns:
        Cleaned string. Empty input returns empty.
    """
    if not text:
        return text

    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    seen: dict = {}
    kept: list = []

    for s in sentences:
        if not s.strip():
            continue
        normalized = re.sub(r"[.,!?\s]+", " ", s.lower()).strip()
        if not normalized:
            kept.append(s)
            continue
        seen[normalized] = seen.get(normalized, 0) + 1
        if seen[normalized] == 1:
            kept.append(s)
        # else: drop the repeat

    return " ".join(kept).strip()


def strip_known_hallucinations(
    text: str,
    extra_phrases: Iterable[str] | None = None,
) -> str:
    """Remove known Whisper hallucination phrases.

    Two modes applied in sequence:
      1. Full-match discard: if the entire transcription matches a known
         phrase (ignoring trailing punctuation), return empty.
      2. Trailing-phantom strip: if the transcription ENDS with a known
         phrase, strip the trailing phrase off but keep the rest.

    Args:
        text: raw or partially-cleaned transcription.
        extra_phrases: additional phrases beyond HALLUCINATIONS (lowercase).

    Returns:
        Cleaned text, or empty string if the entire input was a hallucination.
    """
    if not text:
        return text

    phrases = list(HALLUCINATIONS)
    if extra_phrases:
        phrases.extend(p.lower() for p in extra_phrases)

    stripped = text.strip().lower().rstrip(".,!? ")
    if stripped in phrases:
        return ""

    text_lower = text.lower().rstrip(".!? ")
    for phrase in phrases:
        if text_lower.endswith(phrase):
            cut_at = text_lower.rfind(phrase)
            # Strip trailing whitespace only — preserve the real sentence's
            # terminal punctuation (period, question mark, etc.).
            cleaned = text[:cut_at].rstrip()
            # If what's left is just whitespace or stray punctuation with
            # no word characters, the whole input was hallucination.
            if not re.search(r"\w", cleaned):
                return ""
            return cleaned

    return text


def strip_wake_phrase(text: str, wake_phrases: Iterable[str]) -> str:
    """Remove wake phrases that leaked into the transcription.

    When a wake word is said and the audio capture buffer contains some of it
    by the time recording starts, Whisper transcribes it as part of the
    message. We regex-strip configured wake phrases (and common mishears) out.

    Args:
        text: transcription that may contain wake-phrase residue.
        wake_phrases: iterable of phrases to strip, lowercase or mixed case.

    Returns:
        Text with wake-phrase residue removed. Multi-space collapsed.
    """
    if not text:
        return text

    cleaned = text
    for wp in wake_phrases:
        # Match standard wake phrase
        pattern1 = r"\b" + re.escape(wp) + r"[.,!?\s]*"
        cleaned = re.sub(pattern1, "", cleaned, flags=re.IGNORECASE)
        
        # Match space-separated wake phrase (e.g. cv_over -> cv over)
        if "_" in wp:
            wp_space = wp.replace("_", " ")
            pattern2 = r"\b" + re.escape(wp_space) + r"[.,!?\s]*"
            cleaned = re.sub(pattern2, "", cleaned, flags=re.IGNORECASE)
            
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    return cleaned


def strip_prompt_prefix_hallucination(text: str, initial_prompt: str | None) -> str:
    """If the entire transcribed text (normalized) is a prefix of the initial
    prompt (normalized), it is a silence hallucination and should be discarded.
    """
    if not text or not initial_prompt:
        return text

    def normalize(t: str) -> str:
        # Lowercase, keep only basic letters/digits/spaces
        cleaned = re.sub(r"[^a-z0-9áéíóúàèìòùâêîôûãõçñí\s]", " ", t.lower())
        return " ".join(cleaned.split())

    norm_text = normalize(text)
    norm_prompt = normalize(initial_prompt)

    if not norm_text or not norm_prompt:
        return text

    # Discard if it is a prefix of the prompt and at least 4 characters long
    if len(norm_text) >= 4 and norm_prompt.startswith(norm_text):
        return ""

    return text


def apply_full_pipeline(
    text: str,
    wake_phrases: Iterable[str] | None = None,
    extra_hallucinations: Iterable[str] | None = None,
    initial_prompt: str | None = None,
) -> str:
    """Run all three filters in canonical order.

    Order matters:
      1. Strip repeated sentences first — Whisper's silence loop is the
         most-likely hallucination pattern and produces the cleanest text
         for subsequent filters.
      2. Then known-phrase blacklist — removes pure-hallucination outputs.
      3. Then wake-phrase strip — operates on what's left.
    """
    text = strip_repeated_sentences(text)

    phrases = list(extra_hallucinations) if extra_hallucinations else []
    if initial_prompt:
        phrases.append(initial_prompt)
        sentences = re.split(r"(?<=[.!?])\s+|\n+", initial_prompt)
        for s in sentences:
            s_clean = s.strip()
            if s_clean:
                phrases.append(s_clean)
                s_no_punc = re.sub(r"[.,!?]+", "", s_clean).strip()
                if s_no_punc:
                    phrases.append(s_no_punc)

    text = strip_known_hallucinations(text, extra_phrases=phrases)

    if initial_prompt:
        text = strip_prompt_prefix_hallucination(text, initial_prompt)

    if wake_phrases:
        text = strip_wake_phrase(text, wake_phrases)
    return text
