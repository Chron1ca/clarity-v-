"""
Whisper engine wrapper.

Wraps faster-whisper with:
  - language=None default (auto-detect — NEVER hard-pinned)
  - multi-language initial prompt (en + pt sample sentences)
  - automatic filter chain post-transcribe
  - language reporting on every call

The filter chain that runs on every transcription:
  1. strip_repeated_sentences  (Whisper's silence-loop pattern)
  2. strip_known_hallucinations (YouTube subscribe-prompts etc.)
  3. strip_wake_phrase          (if wake phrases supplied)

Callers receive the cleaned text, the detected language, and the raw
Whisper output for logging/debugging.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from clarity_v import filters

# Multi-language initial prompt — primes Whisper's tokenizer for the
# languages Clarity.V expects to encounter. Adding sentences in another
# language here helps Whisper choose the right tokens.
DEFAULT_INITIAL_PROMPT = (
    "Hello, how are you? I'm doing well. Let me tell you about this. "
    "Olá, como estás? Estou bem. Vamos falar sobre isto."
)


@dataclass
class TranscriptionResult:
    """Output of a single transcribe call."""

    text: str  # cleaned, after filter chain
    language: str  # ISO 639-1 code detected by Whisper
    language_probability: float
    raw_text: str  # raw Whisper output before filters
    duration_seconds: float  # audio duration


class WhisperEngine:
    """Local Whisper STT engine via faster-whisper.

    NEVER pins language by default. Use the language= argument only if you
    explicitly want to force one. Auto-detect is the right default for
    multi-lingual Persons.
    """

    def __init__(
        self,
        model_size: str = "medium",
        device: str = "auto",
        compute_type: str = "float16",
    ) -> None:
        """Load the Whisper model.

        Args:
            model_size: "tiny", "base", "small", "medium" (default), or "large-v3".
                        Medium balances accuracy and speed for general dictation
                        — that's what Clarity.V ships with.
            device: "cuda", "cpu", or "auto" (faster-whisper picks).
            compute_type: "float16" (GPU), "int8" (CPU), "float32" (max accuracy).
        """
        # Local import so test collection / lint doesn't require the package.
        from faster_whisper import WhisperModel

        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str | None = None,
        beam_size: int = 5,
        initial_prompt: str = DEFAULT_INITIAL_PROMPT,
        wake_phrases: Iterable[str] | None = None,
        extra_hallucinations: Iterable[str] | None = None,
    ) -> TranscriptionResult:
        """Transcribe an audio buffer.

        Args:
            audio: numpy array of audio samples. int16 or float32 accepted.
            sample_rate: must be 16000 for Whisper (we don't resample).
            language: ISO code or None for auto-detect (DEFAULT).
            beam_size: 5 is faster-whisper's default; 1 is fastest, 5 is
                       higher quality. Action-word transcribes can use 1.
            initial_prompt: text shown to Whisper as context.
            wake_phrases: phrases to strip from the transcription if they
                          leaked through (e.g. ["clarity-v"]).

        Returns:
            TranscriptionResult with cleaned text, detected language, and
            raw text for logging.
        """
        if sample_rate != 16000:
            raise ValueError(
                f"Whisper requires 16000 Hz, got {sample_rate} Hz. "
                "Resample upstream before calling transcribe()."
            )

        # Normalize to float32 in [-1, 1].
        if audio.dtype == np.int16:
            audio_float = audio.astype(np.float32) / 32768.0
        elif audio.dtype == np.float32:
            audio_float = audio
        else:
            audio_float = audio.astype(np.float32)

        duration = float(len(audio_float)) / sample_rate

        # Run Whisper.
        segments, info = self._model.transcribe(
            audio_float,
            language=language,
            beam_size=beam_size,
            initial_prompt=initial_prompt,
        )
        raw_text = " ".join(seg.text.strip() for seg in segments).strip()

        # Filter chain.
        cleaned = filters.apply_full_pipeline(
            raw_text,
            wake_phrases=list(wake_phrases) if wake_phrases else None,
            extra_hallucinations=extra_hallucinations,
            initial_prompt=initial_prompt,
        )

        return TranscriptionResult(
            text=cleaned,
            language=info.language,
            language_probability=info.language_probability,
            raw_text=raw_text,
            duration_seconds=duration,
        )

    def transcribe_file(
        self,
        wav_path: str | Path,
        **kwargs,
    ) -> TranscriptionResult:
        """Transcribe a WAV file. Convenience wrapper for testing."""
        import wave

        with wave.open(str(wav_path), "rb") as w:
            sample_rate = w.getframerate()
            n_frames = w.getnframes()
            audio_bytes = w.readframes(n_frames)
        audio = np.frombuffer(audio_bytes, dtype=np.int16)
        return self.transcribe(audio, sample_rate=sample_rate, **kwargs)
