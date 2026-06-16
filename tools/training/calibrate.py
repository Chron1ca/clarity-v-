"""
Calibrate wake-word detection threshold against your actual voice.

After training, the model is a classifier producing a score per chunk.
You need to set a *threshold*: scores above it count as detection,
below it don't. Hard-coding `0.5` works in theory but is suboptimal
in practice — every voice + mic + room has different score
distributions. This script measures yours, then sets a threshold
that maximally separates "saying the wake phrase" from "normal speech."

Workflow:
    1. Records you saying the wake phrase 5 times → captures positive
       score distribution (max score per take).
    2. Records 10 s of you talking normally (NOT saying the phrase) →
       captures the negative score floor (max score on speech).
    3. Picks threshold:
       - "GOOD" separation (pos_min > neg_max):
           threshold = (neg_max + pos_min) / 2
       - "PARTIAL" (max(pos) > neg_max but min(pos) <= neg_max):
           threshold = pos_min * 0.8 (some detections will miss)
       - "POOR" (max(pos) <= neg_max):
           model needs retraining; threshold left low
    4. Updates the wake_config.json to use the calibrated value.

Usage:
    python tools/training/calibrate.py \\
        --phrase "cv go" --model path/to/cv_go.onnx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import sounddevice as sd

SAMPLE_RATE = 16000
CHUNK_SIZE = 4000  # 250 ms at 16 kHz, matches AudioCapture default

REPO_ROOT = Path(__file__).parent.parent.parent


def _load_model(model_path: Path):
    from openwakeword.model import Model

    return Model(
        wakeword_models=[str(model_path)],
        inference_framework="onnx",
    )


def _record_and_score(
    model,
    model_name: str,
    duration: float,
):
    """Record `duration` seconds of audio and return per-chunk scores."""
    audio = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    audio = audio.flatten()

    scores = []
    for i in range(0, len(audio) - CHUNK_SIZE, CHUNK_SIZE):
        chunk = audio[i : i + CHUNK_SIZE]
        pred = model.predict(chunk)
        scores.append(pred.get(model_name, 0.0))
    return scores


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phrase",
        required=True,
        help="The wake phrase (for the prompt text).",
    )
    parser.add_argument(
        "--model",
        type=Path,
        required=True,
        help="Path to the trained ONNX model.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="wake_config.json to update. Default: "
        "<repo>/wake_config.json (or skip update if file missing).",
    )
    parser.add_argument(
        "--takes",
        type=int,
        default=5,
        help="Number of positive samples to record.",
    )
    parser.add_argument(
        "--negative-seconds",
        type=int,
        default=10,
        help="Seconds of negative (normal speech) audio to record.",
    )
    args = parser.parse_args()

    if not args.model.exists():
        print(f"[FAIL] Model not found: {args.model}", file=sys.stderr)
        return 1

    model_name = args.model.stem
    print(f"Loading {args.model.name}...", flush=True)
    model = _load_model(args.model)
    print(f"  Loaded as model '{model_name}'\n", flush=True)

    # Phase 1: positive scores.
    print(
        f"PHASE 1 — say {args.phrase!r} {args.takes} times (one per recording).\n",
        flush=True,
    )
    positive_max: list[float] = []
    for i in range(args.takes):
        input(f"  [{i + 1}/{args.takes}] Press Enter, then say {args.phrase!r}: ")
        print("    Recording 3 seconds...", end="", flush=True)
        model.reset()
        scores = _record_and_score(model, model_name, 3.0)
        max_score = float(max(scores)) if scores else 0.0
        positive_max.append(max_score)
        print(f" max score: {max_score:.4f}", flush=True)

    # Phase 2: negative scores.
    print(
        f"\nPHASE 2 — {args.negative_seconds} s of normal speech.\n"
        f"  Talk about ANYTHING except {args.phrase!r}.",
        flush=True,
    )
    input("\n  Press Enter to start: ")
    print(
        f"  Recording {args.negative_seconds} seconds...",
        end="",
        flush=True,
    )
    model.reset()
    neg_scores = _record_and_score(
        model,
        model_name,
        float(args.negative_seconds),
    )
    print(" done", flush=True)

    # Phase 3: analyze.
    # Outlier detection: a take that scored dramatically below the others
    # is almost always a mistimed recording (the user pressed Enter before
    # speaking). Drop takes that score < 10% of the median.
    sorted_positive = sorted(positive_max)
    median = sorted_positive[len(sorted_positive) // 2]
    outliers = [s for s in positive_max if s < median * 0.10]
    effective_positives = [s for s in positive_max if s not in outliers]

    pos_min_raw = min(positive_max)
    pos_max = max(positive_max)
    pos_min = min(effective_positives) if effective_positives else pos_min_raw
    neg_max = float(max(neg_scores)) if neg_scores else 0.0

    print("\n" + "=" * 60)
    print("CALIBRATION RESULTS")
    print("=" * 60)
    print(
        f"  Positive scores ({args.takes} takes): {[round(s, 4) for s in positive_max]}"
    )
    if outliers:
        print(
            f"  Outliers excluded (mistimed takes, score < 10% of median): "
            f"{[round(s, 4) for s in outliers]}"
        )
    print(f"  Positive min / max (after outliers): {pos_min:.4f} / {pos_max:.4f}")
    print(f"  Negative max:                       {neg_max:.4f}")

    if pos_min > neg_max:
        recommended = (neg_max + pos_min) / 2
        verdict = "GOOD"
        notes = "Clean separation — picks up your wake word reliably."
    elif pos_max > neg_max:
        recommended = pos_min * 0.8
        verdict = "PARTIAL"
        notes = (
            "Some positives overlap with negatives — will miss some "
            "detections. More training data (especially real-voice) helps."
        )
    else:
        recommended = max(0.1, pos_max * 0.5)
        verdict = "POOR"
        notes = (
            "Negatives match or exceed positives — model is not yet "
            "well-trained. Consider more synthetic samples (--n-samples) "
            "or more real-voice clips (import_real_clips.py)."
        )

    print(f"\n  Separation: {verdict}")
    print(f"  Recommended threshold: {recommended:.3f}")
    print(f"  Notes: {notes}\n")

    # Phase 4: update config. Create wake_config.json if it doesn't exist.
    config_path = args.config or (REPO_ROOT / "wake_config.json")
    if not config_path.exists():
        print(f"  No wake_config.json at {config_path} — creating it.")
        config: dict = {"models": [], "cooldown_seconds": 0.5}
    else:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(
                f"  Could not parse {config_path}: {e}\n"
                f"  Threshold {recommended:.3f} not written.",
                file=sys.stderr,
            )
            return 1

    updated = False
    for m in config.get("models", []):
        if m.get("name") == model_name:
            m["threshold"] = round(recommended, 3)
            updated = True

    if not updated:
        # Add a new entry. Infer role from naming convention:
        # *_go / *_start / *_begin → start; *_over / *_stop / *_end → stop.
        # Default to "start" if unclear.
        lowered = model_name.lower()
        if any(suffix in lowered for suffix in ("over", "stop", "end")):
            role = "stop"
        else:
            role = "start"
        config.setdefault("models", []).append(
            {
                "name": model_name,
                "model_path": str(args.model),
                "threshold": round(recommended, 3),
                "role": role,
            }
        )

    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Updated {config_path}")
    print("  Restart Clarity.V to apply.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
