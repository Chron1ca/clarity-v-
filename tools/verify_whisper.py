"""
Phase 2 verification: Whisper engine works locally, auto-detects language.

Tests:
  1. Engine loads (Medium model, default device).
  2. Silence input → empty text after filter chain (no hallucination).
  3. If tests/fixtures/sample_en.wav exists → detects 'en', non-empty text.
  4. If tests/fixtures/sample_pt.wav exists → detects 'pt', non-empty text.

Exit code 0 only when ALL applicable tests pass. Missing fixtures are
flagged as BLOCKED, not skipped silently — Phase 2 isn't complete until
both fixtures exist and pass.

Usage:
    python tools/verify_whisper.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np

from clarity_v.whisper_engine import WhisperEngine


FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def _print(level: str, msg: str) -> None:
    print(f"  [{level:8s}] {msg}")


def test_engine_loads() -> WhisperEngine:
    print("\n[1/4] Engine load")
    _print("INFO", "Loading Whisper Medium (~1.5 GB, first run downloads)...")
    engine = WhisperEngine(model_size="medium")
    _print("OK", f"Model loaded: {engine.model_size} on {engine.device}")
    return engine


def test_silence_handling(engine: WhisperEngine) -> bool:
    """Silence audio should produce empty text after the filter chain."""
    print("\n[2/4] Silence handling")
    silence = np.zeros(16000 * 3, dtype=np.int16)  # 3 seconds of silence
    result = engine.transcribe(silence)
    _print("INFO", f"raw_text={result.raw_text!r}")
    _print("INFO", f"cleaned={result.text!r}")
    _print("INFO", f"language={result.language} p={result.language_probability:.2f}")
    # Either raw was empty OR the filter chain stripped it.
    if not result.text:
        _print("OK", "Silence → empty after filters")
        return True
    _print("FAIL", f"Silence produced non-empty text: {result.text!r}")
    return False


def test_real_audio(engine: WhisperEngine, wav_name: str, expected_lang: str) -> bool:
    """Real audio: detected language matches, text is non-empty."""
    print(f"\n[3-4/4] {wav_name} ({expected_lang.upper()})")
    wav_path = FIXTURES_DIR / wav_name
    if not wav_path.exists():
        _print("BLOCKED", f"Missing fixture: {wav_path}")
        _print("BLOCKED", "Run: python tools/record_fixtures.py")
        return False
    result = engine.transcribe_file(wav_path)
    _print("INFO", f"raw_text={result.raw_text!r}")
    _print("INFO", f"cleaned={result.text!r}")
    _print(
        "INFO",
        f"language={result.language} p={result.language_probability:.2f} "
        f"duration={result.duration_seconds:.1f}s",
    )
    ok_lang = result.language == expected_lang
    ok_text = len(result.text) > 3
    if ok_lang and ok_text:
        _print("OK", f"{expected_lang.upper()} detected and transcribed")
        return True
    if not ok_lang:
        _print("FAIL", f"Expected language={expected_lang}, got {result.language}")
    if not ok_text:
        _print("FAIL", f"Transcription too short: {result.text!r}")
    return False


def main() -> int:
    print("=" * 60)
    print("Clarity.V Phase 2 — Whisper engine verification")
    print("=" * 60)

    results = {}

    try:
        engine = test_engine_loads()
    except Exception as e:
        _print("FAIL", f"Engine load: {type(e).__name__}: {e}")
        return 1

    results["silence"] = test_silence_handling(engine)
    results["en"] = test_real_audio(engine, "sample_en.wav", "en")
    results["pt"] = test_real_audio(engine, "sample_pt.wav", "pt")

    print("\n" + "=" * 60)
    print("Summary:")
    for name, passed in results.items():
        mark = "OK" if passed else "FAIL/BLOCKED"
        print(f"  {mark:13s} {name}")
    all_pass = all(results.values())
    print("=" * 60)
    print("PHASE 2 COMPLETE" if all_pass else "PHASE 2 INCOMPLETE")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
