"""
Record sample WAVs for Phase 2 verification.

Run once. Records two 5-second clips (one English, one Portuguese) to
tests/fixtures/ for Whisper engine verification.

Usage:
    python tools/record_fixtures.py
"""

from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd


REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
SAMPLE_RATE = 16000
DURATION = 5  # seconds per clip


def record_clip(language_name: str, suggested_phrase: str) -> np.ndarray:
    print(f"\n=== Recording {language_name} sample ===")
    print(f"You will speak for {DURATION} seconds.")
    print(f"Suggested phrase: {suggested_phrase!r}")
    input("Press Enter when ready, then speak immediately...")

    print(f"Recording for {DURATION} seconds...")
    audio = sd.rec(
        int(DURATION * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
    )
    for i in range(DURATION):
        print(f"  {DURATION - i}...")
        time.sleep(1)
    sd.wait()
    print("Done.")
    return audio.flatten()


def save_wav(audio: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # int16 = 2 bytes
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())
    print(f"Saved: {path}")


def main() -> int:
    print("Clarity.V — fixture recorder")
    print("This will record two short clips for Whisper verification.")
    print(f"Output: {FIXTURES_DIR}")

    # English
    en_audio = record_clip(
        "ENGLISH", "Hello, this is a test of the Clarity.V dictation system."
    )
    save_wav(en_audio, FIXTURES_DIR / "sample_en.wav")

    # Portuguese
    pt_audio = record_clip(
        "PORTUGUESE", "Olá, isto é um teste do sistema de ditado Clarity.V."
    )
    save_wav(pt_audio, FIXTURES_DIR / "sample_pt.wav")

    print("\nDone. Run verification with:")
    print("    python tools/verify_whisper.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
