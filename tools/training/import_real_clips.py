"""
Import real-voice audio (m4a / mp3 / wav) into training data.

Decodes a long-form recording with ffmpeg → 16 kHz mono int16 →
detects individual utterances via per-frame RMS energy → pads or
center-crops each to exactly 2.0 s → writes them as `real_NNNN.wav`
into `positive_train/` and `positive_test/` (80/20 split) under
the model's output directory.

Why this exists: TTS-generated samples cover voice variety in general
but not YOUR voice in YOUR room. Mixing 50-200 real recordings into
the synthetic training set produces a model that fires reliably on
you specifically. You can record a single long voice memo on your
phone saying the wake phrase many times naturally, then this script
chops it into individual training clips.

Workflow:
    1. python tools/training/train.py --phrase "cv go" --model-name cv_go \\
           --stop-after generate                          # generate synth
    2. python tools/training/import_real_clips.py \\
           --source path/to/voice_memo.m4a \\
           --model-name cv_go                             # inject real clips
    3. python tools/training/train.py --phrase "cv go" --model-name cv_go
                                                          # finish training

Energy gating:
    Per-frame RMS computed at 20 ms frames. Threshold is the stricter
    of (percentile_55, min_db=-45 dBFS). Frames above are "active";
    adjacent active frames merge into utterances. Gaps shorter than
    250 ms are absorbed into the surrounding utterance; utterances
    shorter than 300 ms are dropped.

Requirements:
    ffmpeg available on PATH, or its path provided via --ffmpeg.
    numpy + scipy.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wav

SAMPLE_RATE = 16000
CLIP_SECONDS = 2.0
CLIP_SAMPLES = int(SAMPLE_RATE * CLIP_SECONDS)

REPO_ROOT = Path(__file__).parent.parent.parent


def _decode_to_int16(source: Path, ffmpeg: str) -> np.ndarray:
    """Run ffmpeg to decode any audio file to 16 kHz mono s16le PCM."""
    if not source.exists():
        raise FileNotFoundError(f"Source audio not found: {source}")

    cmd = [
        ffmpeg,
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "pipe:1",
    ]
    print(f"  Decoding: {source.name}", flush=True)
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg failed (exit {result.returncode}):\n{err}")
    audio = np.frombuffer(result.stdout, dtype=np.int16)
    duration = len(audio) / SAMPLE_RATE
    print(f"  Decoded: {len(audio)} samples ({duration:.1f}s)", flush=True)
    return audio


def _detect_utterances(
    audio: np.ndarray,
    *,
    frame_ms: int = 20,
    min_utterance_ms: int = 300,
    min_silence_ms: int = 250,
    energy_percentile: float = 55.0,
    min_energy_db: float = -45.0,
) -> list[tuple[int, int]]:
    """Return (start_sample, end_sample) for each detected utterance.

    Per-frame RMS in dBFS, threshold = max(percentile, min_db). Frames
    above threshold are "active". Adjacent active frames merge; gaps
    shorter than min_silence_ms are absorbed; utterances shorter than
    min_utterance_ms are dropped.
    """
    frame_len = int(SAMPLE_RATE * frame_ms / 1000)
    n_frames = len(audio) // frame_len
    if n_frames == 0:
        return []

    frames = audio[: n_frames * frame_len].reshape(n_frames, frame_len)
    frames_f = frames.astype(np.float32)
    rms = np.sqrt(np.mean(frames_f**2, axis=1) + 1e-9)
    rms_db = 20 * np.log10(rms / 32768.0 + 1e-12)

    pct_threshold = np.percentile(rms_db, energy_percentile)
    threshold_db = max(pct_threshold, min_energy_db)
    active = rms_db > threshold_db

    print(
        f"  Frame energy: median={np.median(rms_db):.1f}dB "
        f"p55={pct_threshold:.1f}dB threshold={threshold_db:.1f}dB "
        f"active_frames={active.sum()}/{n_frames}",
        flush=True,
    )

    min_silence_frames = max(1, min_silence_ms // frame_ms)
    min_utt_frames = max(1, min_utterance_ms // frame_ms)

    utterances = []
    i = 0
    while i < n_frames:
        if not active[i]:
            i += 1
            continue
        start = i
        j = i + 1
        last_active = i
        while j < n_frames:
            if active[j]:
                last_active = j
                j += 1
                continue
            # Look ahead — is this a short gap or end-of-utterance?
            gap_end = j
            while gap_end < n_frames and not active[gap_end]:
                gap_end += 1
            if gap_end - j >= min_silence_frames:
                break
            j = gap_end
        end = last_active + 1
        if end - start >= min_utt_frames:
            utterances.append((start * frame_len, end * frame_len))
        i = j

    print(f"  Detected {len(utterances)} utterances", flush=True)
    return utterances


def _trim_silence(
    audio: np.ndarray,
    threshold: int = 500,
    pad_samples: int = 1600,
) -> np.ndarray:
    """Trim leading/trailing silence; keep ~100 ms padding on each end."""
    above = np.abs(audio) > threshold
    if not above.any():
        return audio
    first = max(0, int(np.argmax(above)) - pad_samples)
    last = min(
        len(audio),
        len(audio) - int(np.argmax(above[::-1])) + pad_samples,
    )
    return audio[first:last]


def _pad_or_crop(utterance: np.ndarray) -> np.ndarray:
    """Pad with zeros or center-crop so output is exactly CLIP_SAMPLES."""
    if len(utterance) >= CLIP_SAMPLES:
        excess = len(utterance) - CLIP_SAMPLES
        start = excess // 2
        return utterance[start : start + CLIP_SAMPLES]
    pad_total = CLIP_SAMPLES - len(utterance)
    left = pad_total // 2
    right = pad_total - left
    return np.concatenate(
        [
            np.zeros(left, dtype=np.int16),
            utterance,
            np.zeros(right, dtype=np.int16),
        ]
    )


def _next_real_index(train_dir: Path, test_dir: Path) -> int:
    """Return next index after the highest existing real_NNNN.wav."""
    highest = -1
    for d in (train_dir, test_dir):
        for f in d.glob("real_*.wav"):
            try:
                idx = int(f.stem.split("_", 1)[1])
                highest = max(highest, idx)
            except (ValueError, IndexError):
                continue
    return highest + 1


def main() -> int:
    # Short ASCII description (not __doc__) so argparse --help renders on
    # Windows cp1252 consoles — the module docstring uses em-dashes and
    # arrows that crash the default Windows codec.
    parser = argparse.ArgumentParser(
        description=(
            "Import real-voice audio (m4a / mp3 / wav) into a "
            "wake-word training data directory."
        ),
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to source audio (m4a, mp3, wav, etc.)",
    )
    parser.add_argument(
        "--model-name",
        required=True,
        help="Model name (matches train.py --model-name). Clips go under "
        "<data-dir>/my_custom_model/<model-name>/positive_{train,test}/.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Training data directory. Default: ./models/training_data/",
    )
    parser.add_argument(
        "--ffmpeg",
        default=shutil.which("ffmpeg") or "ffmpeg",
        help="Path to ffmpeg binary.",
    )
    parser.add_argument(
        "--min-db",
        type=float,
        default=-45.0,
        help="Minimum frame energy threshold in dBFS.",
    )
    parser.add_argument(
        "--pct",
        type=float,
        default=55.0,
        help="Energy percentile for adaptive threshold (0-100).",
    )
    parser.add_argument("--min-utt-ms", type=int, default=300)
    parser.add_argument("--min-silence-ms", type=int, default=250)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect and report only; don't write files.",
    )
    args = parser.parse_args()

    data_dir = args.data_dir or (REPO_ROOT / "models" / "training_data")
    model_name = args.model_name
    train_dir = data_dir / "my_custom_model" / model_name / "positive_train"
    test_dir = data_dir / "my_custom_model" / model_name / "positive_test"

    if not train_dir.exists() or not test_dir.exists():
        print(
            f"[FAIL] Positive dirs do not exist:\n"
            f"       {train_dir}\n"
            f"       {test_dir}\n"
            f"       Run `train.py --phrase ... --model-name {model_name} "
            f"--stop-after generate` first to create the layout.",
            file=sys.stderr,
        )
        return 1

    if not Path(args.ffmpeg).exists() and shutil.which(args.ffmpeg) is None:
        print(
            f"[FAIL] ffmpeg not found at {args.ffmpeg}. "
            "Install ffmpeg or pass --ffmpeg /path/to/ffmpeg.",
            file=sys.stderr,
        )
        return 1

    audio = _decode_to_int16(args.source, args.ffmpeg)
    regions = _detect_utterances(
        audio,
        min_utterance_ms=args.min_utt_ms,
        min_silence_ms=args.min_silence_ms,
        energy_percentile=args.pct,
        min_energy_db=args.min_db,
    )

    if not regions:
        print(
            "[FAIL] No utterances detected. Try lowering --min-db or --pct.",
            file=sys.stderr,
        )
        return 1

    start_idx = _next_real_index(train_dir, test_dir)
    print(f"  Starting real_ index at {start_idx:04d}", flush=True)

    written_train = 0
    written_test = 0
    for i, (start, end) in enumerate(regions):
        utterance = audio[start:end]
        utterance = _trim_silence(utterance)
        if len(utterance) < int(SAMPLE_RATE * 0.3):
            print(
                f"  [{i + 1}/{len(regions)}] skipped (too short after trim)",
                flush=True,
            )
            continue
        clip = _pad_or_crop(utterance)

        idx = start_idx + i
        # 80/20: every 5th sample goes to test.
        if (i + 1) % 5 == 0:
            dest = test_dir / f"real_{idx:04d}.wav"
            split = "test"
            written_test += 1
        else:
            dest = train_dir / f"real_{idx:04d}.wav"
            split = "train"
            written_train += 1

        start_s = start / SAMPLE_RATE
        if args.dry_run:
            print(
                f"  [{i + 1}/{len(regions)}] DRY {split} @ {start_s:5.1f}s "
                f"-> {dest.name}",
                flush=True,
            )
        else:
            wav.write(str(dest), SAMPLE_RATE, clip.astype(np.int16))
            print(
                f"  [{i + 1}/{len(regions)}] {split} @ {start_s:5.1f}s -> {dest.name}",
                flush=True,
            )

    total_train = len(list(train_dir.glob("*.wav")))
    total_test = len(list(test_dir.glob("*.wav")))
    print()
    print(
        f"  Wrote {written_train} train + {written_test} test clips",
        flush=True,
    )
    print(
        f"  Total (synthetic + real): {total_train} train, {total_test} test",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
