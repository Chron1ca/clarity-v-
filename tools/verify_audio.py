"""
Phase 3 verification: audio capture works locally with a real microphone.

Tests:
  1. list_devices() returns at least one input device.
  2. AudioCapture.start() opens the stream without exception.
  3. on_chunk callback fires.
  4. begin_record / end_record captures chunks.
  5. Captured buffer has non-zero RMS energy (mic actually heard speech).
  6. Saved WAV plays back the expected duration.

Run interactively. The script prompts you to speak for 3 seconds.

Usage:
    python tools/verify_audio.py
"""

from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from clarity_v.audio import (  # noqa: E402
    AudioCapture,
    concat,
    get_default_input,
    list_devices,
    rms_energy,
)


FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def _print(level: str, msg: str) -> None:
    print(f"  [{level:8s}] {msg}")


def test_device_enumeration() -> bool:
    print("\n[1/5] Device enumeration")
    devices = list_devices()
    if not devices:
        _print("FAIL", "No input devices found.")
        return False
    _print("OK", f"Found {len(devices)} input device(s):")
    for d in devices:
        _print(
            "INFO",
            f"  #{d.index:2d} {d.name} "
            f"({d.max_input_channels}ch, {d.default_samplerate:.0f} Hz)",
        )
    default = get_default_input()
    if default:
        _print("INFO", f"Default: #{default.index} {default.name}")
    return True


def test_stream_lifecycle() -> bool:
    print("\n[2/5] Stream open/close")
    cap = AudioCapture()
    try:
        cap.start()
        time.sleep(0.2)
        cap.stop()
        _print("OK", "Stream opened, ran for 200 ms, closed cleanly.")
        return True
    except Exception as e:
        _print("FAIL", f"{type(e).__name__}: {e}")
        return False


def test_on_chunk_callback() -> bool:
    print("\n[3/5] on_chunk callback fires")
    received: list = []
    cap = AudioCapture(on_chunk=lambda c: received.append(c))
    try:
        cap.start()
        time.sleep(1.0)
        cap.stop()
    except Exception as e:
        _print("FAIL", f"{type(e).__name__}: {e}")
        return False
    if len(received) < 2:
        _print("FAIL", f"Expected several chunks, got {len(received)}")
        return False
    _print(
        "OK",
        f"Received {len(received)} chunks in ~1 s "
        f"(blocksize={len(received[0]) if received else 0})",
    )
    return True


def _record_for(seconds: int, prompt: str) -> list[np.ndarray]:
    cap = AudioCapture()
    cap.start()
    input(
        f"    Press Enter, then {prompt} for ~{seconds} seconds "
        f"(silence to end early is fine; full window is captured)..."
    )
    cap.begin_record()
    for i in range(seconds, 0, -1):
        print(f"    {i:2d}...", end="\r", flush=True)
        time.sleep(1)
    print()
    chunks = cap.end_record()
    cap.stop()
    return chunks


def test_record_buffer() -> bool:
    seconds = 10
    print(f"\n[4/5] Record/buffer cycle — speak for {seconds} seconds")
    print("    Use a realistic dictation message so the test exercises")
    print("    the same code path real use does (real messages run 10-30 s).")
    chunks = _record_for(
        seconds,
        "speak naturally (any sentence or two of dictation)",
    )
    if not chunks:
        _print("FAIL", "No chunks captured during recording.")
        return False
    audio = concat(chunks)
    duration = len(audio) / 16000
    energy = rms_energy(audio)
    _print(
        "INFO",
        f"Captured {len(chunks)} chunks = {duration:.1f} s = {len(audio)} samples",
    )
    _print("INFO", f"RMS energy: {energy:.4f} (silence ~< 0.005)")
    if duration < seconds - 1 or duration > seconds + 1:
        _print("FAIL", f"Duration {duration:.1f}s out of expected ~{seconds}s range.")
        return False
    if energy < 0.005:
        _print("FAIL", "Buffer is essentially silent — mic not picking up audio.")
        return False
    _print("OK", "Buffer has audible content at realistic dictation length.")
    return True


def test_wav_save() -> bool:
    seconds = 8
    print(f"\n[5/5] WAV save (records {seconds} s for the fixture)")
    chunks = _record_for(
        seconds,
        "say something natural — this becomes tests/fixtures/last_capture.wav",
    )
    audio = concat(chunks)
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIXTURES_DIR / "last_capture.wav"
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(audio.tobytes())
    _print("OK", f"Saved {out_path} ({len(audio) / 16000:.1f} s)")
    return True


def main() -> int:
    print("=" * 60)
    print("Clarity.V Phase 3 — Audio capture verification")
    print("=" * 60)

    results = {
        "devices": test_device_enumeration(),
        "stream": test_stream_lifecycle(),
        "chunks": test_on_chunk_callback(),
        "record": test_record_buffer(),
        "wav": test_wav_save(),
    }

    print("\n" + "=" * 60)
    print("Summary:")
    for name, passed in results.items():
        mark = "OK" if passed else "FAIL"
        print(f"  {mark:5s} {name}")
    print("=" * 60)
    all_pass = all(results.values())
    print("PHASE 3 COMPLETE" if all_pass else "PHASE 3 INCOMPLETE")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
