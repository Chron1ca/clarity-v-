"""
Generate synthetic background noise for wake-word training augmentation.

Wake-word training works by mixing positive samples (your wake phrase)
against negative audio (everything-else). The "everything-else" can be
either a large pre-computed feature file (5-17 GB download) OR
locally-generated synthetic noise. This script generates the latter:

  - White noise at several amplitude levels
  - Pink noise (1/f spectrum, filtered)
  - Mains hum at 50/60/100/120 Hz + low-level noise
  - Ambient base with random short bursts (mimics room noise + activity)

~80 thirty-second WAVs total. Useful when you don't want the big
ACAV100M download. The synthetic noise is mixed alongside any
real-world negatives in the training config.

Usage:
    python tools/training/generate_background_noise.py
    python tools/training/generate_background_noise.py \\
        --out path/to/background_noise/

Output:
    <out>/white_<level>_<i>.wav
    <out>/pink_<level>_<i>.wav
    <out>/hum_<freq>hz_<level>.wav
    <out>/ambient_<i>.wav
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import scipy.io.wavfile
from scipy.signal import lfilter

SAMPLE_RATE = 16000
DURATION_S = 30
N_SAMPLES = SAMPLE_RATE * DURATION_S

REPO_ROOT = Path(__file__).parent.parent.parent


def _save(path: Path, samples: np.ndarray) -> None:
    scipy.io.wavfile.write(str(path), SAMPLE_RATE, samples.astype(np.int16))


def _white_noise(out_dir: Path, rng: np.random.Generator) -> int:
    """Six amplitude levels × 10 variations each."""
    n = 0
    for level in [0.01, 0.02, 0.05, 0.10, 0.15, 0.20]:
        for i in range(10):
            samples = rng.standard_normal(N_SAMPLES) * level * 32767
            _save(out_dir / f"white_{level:.2f}_{i:02d}.wav", samples)
            n += 1
    return n


def _pink_noise(out_dir: Path, rng: np.random.Generator) -> int:
    """1/f-filtered noise at four amplitude levels."""
    # Approximate pink-noise filter coefficients.
    b = [0.049922035, -0.095993537, 0.050612699, -0.004709510]
    a = [1.0, -2.494956002, 2.017265875, -0.522189400]
    n = 0
    for level in [0.02, 0.05, 0.10, 0.15]:
        for i in range(10):
            white = rng.standard_normal(N_SAMPLES)
            pink = lfilter(b, a, white)
            peak = max(abs(pink.max()), abs(pink.min()))
            pink = pink / peak * level * 32767
            _save(out_dir / f"pink_{level:.2f}_{i:02d}.wav", pink)
            n += 1
    return n


def _mains_hum(out_dir: Path, rng: np.random.Generator) -> int:
    """50/60 Hz mains hum + 2nd harmonics at three amplitude levels."""
    n = 0
    t = np.linspace(0, DURATION_S, N_SAMPLES)
    for freq in [50, 60, 100, 120]:
        for level in [0.02, 0.05, 0.10]:
            hum = np.sin(2 * np.pi * freq * t) * level
            # Light noise on top
            hum = hum + rng.standard_normal(N_SAMPLES) * 0.01
            samples = hum * 32767
            _save(
                out_dir / f"hum_{freq}hz_{level:.2f}.wav",
                samples,
            )
            n += 1
    return n


def _ambient(out_dir: Path, rng: np.random.Generator, count: int = 20) -> int:
    """Quiet base + a handful of random bursts (room ambient pattern)."""
    n = 0
    for i in range(count):
        ambient = rng.standard_normal(N_SAMPLES) * 0.005
        n_bursts = int(rng.integers(3, 10))
        for _ in range(n_bursts):
            start = int(rng.integers(0, N_SAMPLES - SAMPLE_RATE))
            length = int(rng.integers(SAMPLE_RATE // 4, SAMPLE_RATE * 2))
            end = min(start + length, N_SAMPLES)
            burst = rng.standard_normal(end - start)
            burst *= float(rng.uniform(0.02, 0.15))
            ambient[start:end] = ambient[start:end] + burst
        samples = ambient * 32767
        _save(out_dir / f"ambient_{i:02d}.wav", samples)
        n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory. Default: models/training_data/background_noise/",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed (for reproducibility).",
    )
    parser.add_argument(
        "--ambient-count",
        type=int,
        default=20,
        help="Number of ambient/burst files to generate.",
    )
    args = parser.parse_args()

    out_dir = args.out or (REPO_ROOT / "models" / "training_data" / "background_noise")
    out_dir.mkdir(parents=True, exist_ok=True)

    existing = list(out_dir.glob("*.wav"))
    if len(existing) > 10:
        print(
            f"Found {len(existing)} files already in {out_dir}",
            flush=True,
        )
        print(
            "  Skipping generation. Delete them first if you want to regenerate.",
            flush=True,
        )
        return 0

    rng = np.random.default_rng(args.seed)
    print(f"Generating synthetic background noise -> {out_dir}", flush=True)

    total = 0
    total += _white_noise(out_dir, rng)
    total += _pink_noise(out_dir, rng)
    total += _mains_hum(out_dir, rng)
    total += _ambient(out_dir, rng, count=args.ambient_count)

    print(f"\nGenerated {total} background-noise WAVs.", flush=True)
    print(
        f"  Total size: ~{total * N_SAMPLES * 2 / (1024 * 1024):.0f} MB",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
