"""
Record the Person's own voice saying the wake phrase, then augment.

Why: TTS samples cover voice variety but not YOUR voice specifically.
Mixing 20-30 of your own recordings (augmented to ~500) into the
positive training set produces a wake-word model that responds best
to you in your room with your mic.

Workflow:
  1. The script prompts you to say the phrase N times (default 25).
  2. After each take, it saves a clean WAV.
  3. Then it augments each recording to produce many synthetic variants
     (pitch shift, time stretch, light noise) — typically 20x per take.
  4. Outputs go into the SAME positive/ directory used by
     generate_samples.py, so training mixes synthetic + personal.

Usage:
    python tools/training/record_personal_voice.py \\
        --phrase "cv go" --model-name cv_go

    python tools/training/record_personal_voice.py \\
        --phrase "computer" --model-name computer --takes 30

Samples land in:
    <data-dir>/my_custom_model/<model-name>/positive_train/   (80%)
    <data-dir>/my_custom_model/<model-name>/positive_test/    (20%)

This matches the layout train.py reads — same --model-name + --data-dir
flags as generate_samples.py and import_real_clips.py.

Recommended: 20-30 takes. More is better but diminishing returns.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import sys
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd


SAMPLE_RATE = 16000
TAKE_DURATION_SECONDS = 2  # generous; wake phrase usually 0.5-1.2 s

REPO_ROOT = Path(__file__).parent.parent.parent


def _safe_filename(phrase: str) -> str:
    s = re.sub(r"[^\w]+", "_", phrase.lower()).strip("_")
    return s or "wakeword"


def _record_take(seconds: int) -> np.ndarray:
    audio = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    return audio.flatten()


def _save_wav(audio: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())


def _trim_silence(audio: np.ndarray, threshold: float = 0.01) -> np.ndarray:
    """Trim leading/trailing silence so each sample is the wake phrase only."""
    if len(audio) == 0:
        return audio
    f = audio.astype(np.float32) / 32768.0
    abs_f = np.abs(f)
    # Find first and last samples above threshold.
    above = np.where(abs_f > threshold)[0]
    if len(above) == 0:
        return audio  # all silence — leave it; the augmentation step skips
    start = max(0, above[0] - int(0.05 * SAMPLE_RATE))  # 50 ms padding
    end = min(len(audio), above[-1] + int(0.1 * SAMPLE_RATE))  # 100 ms tail
    return audio[start:end]


def _augment_one(audio: np.ndarray, seed: int) -> np.ndarray:
    """Apply a randomized augmentation to a take.

    Light transforms only — heavy distortion harms training. We use:
      - pitch shift: ±200 cents (±2 semitones)
      - time stretch: 0.92-1.08x
      - amplitude scaling: 0.7-1.0
      - low-level white noise: SNR 30-50 dB
    Returns int16 ndarray. Falls back to original on any failure so
    the dataset is never blocked by an augmentation bug.
    """
    try:
        import librosa
    except ImportError:
        # No augmentation library — return original.
        return audio

    rng = np.random.default_rng(seed)
    f = audio.astype(np.float32) / 32768.0

    # Time stretch
    rate = float(rng.uniform(0.92, 1.08))
    with contextlib.suppress(Exception):
        f = librosa.effects.time_stretch(f, rate=rate)

    # Pitch shift (cents → semitones)
    cents = float(rng.uniform(-200, 200))
    n_steps = cents / 100.0
    with contextlib.suppress(Exception):
        f = librosa.effects.pitch_shift(f, sr=SAMPLE_RATE, n_steps=n_steps)

    # Amplitude scaling
    gain = float(rng.uniform(0.7, 1.0))
    f = f * gain

    # Light noise
    snr_db = float(rng.uniform(30, 50))
    noise_amp = float(np.sqrt(np.mean(f * f))) * (10 ** (-snr_db / 20))
    f = f + rng.standard_normal(len(f)).astype(np.float32) * noise_amp

    # Clip + back to int16
    f = np.clip(f, -1.0, 1.0)
    return (f * 32767).astype(np.int16)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record + augment personal-voice wake-word samples."
    )
    parser.add_argument(
        "--phrase", required=True, help="Wake phrase to record (e.g., 'cv go')."
    )
    parser.add_argument(
        "--model-name",
        default=None,
        help="Model directory name (matches train.py --model-name). "
        "Defaults to a safe transform of --phrase. Samples land in "
        "<data-dir>/my_custom_model/<model-name>/positive_{train,test}.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Training data root. Default: <repo>/models/training_data/. "
        "Must match the --data-dir you'll pass to train.py.",
    )
    parser.add_argument(
        "--takes",
        type=int,
        default=25,
        help="Number of voice takes to record (default 25).",
    )
    parser.add_argument(
        "--augments-per-take",
        type=int,
        default=20,
        help="Number of augmented variants per take "
        "(default 20 -> 25 takes x 20 = 500 samples).",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="personal",
        help="Filename prefix for personal samples "
        "(default 'personal'; lets you mix with TTS).",
    )
    args = parser.parse_args()

    safe_name = _safe_filename(args.model_name or args.phrase)
    data_dir = args.data_dir or (REPO_ROOT / "models" / "training_data")
    model_root = data_dir / "my_custom_model" / safe_name
    train_dir = model_root / "positive_train"
    test_dir = model_root / "positive_test"
    train_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    print(f"Phrase:            {args.phrase!r}")
    print(f"Model name:        {safe_name!r}")
    print(f"Takes:             {args.takes}")
    print(f"Augments per take: {args.augments_per_take}")
    print(f"Total samples:     {args.takes * (1 + args.augments_per_take)}")
    print(f"Output train:      {train_dir.resolve()}")
    print(f"Output test:       {test_dir.resolve()}")
    print()
    print("Tips for good takes:")
    print("  - Say the phrase naturally, the way you'll say it in real use.")
    print("  - Vary slightly between takes: louder/softer, faster/slower,")
    print("    different distances from the mic, different angles.")
    print("  - Do NOT speak the phrase the same way every time.")
    print("  - Quiet room helps but isn't critical.")
    print()
    input("Press Enter to start. You'll have 2 seconds per take.")

    sample_idx = 0
    for take_n in range(1, args.takes + 1):
        # 80/20 split BY TAKE so each take's clean + augments stay
        # together — every 5th take lands in positive_test, the rest
        # in positive_train. Same split pattern as generate_samples
        # and import_real_clips.
        out_dir = test_dir if take_n % 5 == 0 else train_dir
        print(f"\n--- Take {take_n}/{args.takes} ({out_dir.name}) ---")
        print(f"  Say: {args.phrase!r}")
        for c in range(3, 0, -1):
            print(f"  {c}...")
            time.sleep(0.5)
        print("  RECORDING")
        audio = _record_take(TAKE_DURATION_SECONDS)
        audio = _trim_silence(audio)
        if len(audio) < int(SAMPLE_RATE * 0.2):
            print("  (Too short, skipped - speak louder/closer next take)")
            continue
        print(f"  Captured ({len(audio) / SAMPLE_RATE:.2f}s)")

        # Save the clean take.
        clean_path = out_dir / f"{args.prefix}_take{take_n:03d}_clean.wav"
        _save_wav(audio, clean_path)
        sample_idx += 1

        # Augment.
        for k in range(args.augments_per_take):
            aug = _augment_one(audio, seed=take_n * 1000 + k)
            aug_path = out_dir / f"{args.prefix}_take{take_n:03d}_aug{k:03d}.wav"
            _save_wav(aug, aug_path)
            sample_idx += 1

    print()
    print(f"Done. {sample_idx} personal samples saved to {model_root}")
    print()
    print(
        "Next: run `python tools/training/generate_samples.py "
        f"--phrase {args.phrase!r} --model-name {safe_name} --target 5000` "
        "for synthetic samples, then "
        f"`python tools/training/train.py --phrase {args.phrase!r} "
        f"--model-name {safe_name}` to train."
    )
    print("See TRAINING.md for the full pipeline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
