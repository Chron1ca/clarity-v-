"""
Train a custom wake-word model.

End-to-end pipeline: generate synthetic clips → augment with noise +
reverb → train an ONNX classifier. Each stage's output is checked
before running, so re-runs skip already-completed stages (full
generate + augment + train takes hours; iteration becomes
unbearable without stage skipping).

Usage:
    python tools/training/train.py --phrase "cv go" --model-name cv_go

    # Reuse an existing training data directory (e.g., shared with
    # another model that already downloaded the negatives):
    python tools/training/train.py --phrase "cv over" --model-name cv_over \\
        --data-dir D:/path/to/shared/training_data

Requirements:
    Run from the dedicated training venv. See tools/training/requirements.txt.
    Training on a CUDA GPU takes ~1-2 hours per model; CPU takes 6-12 hours.

Output:
    models/wake_words/<model_name>.onnx (and optionally .onnx.data)

Implementation notes:
- All training steps run via _train_step_wrapper.py, which patches
  torchaudio for Windows compatibility (the released torchaudio
  removed `set_audio_backend`, which OpenWakeWord still imports).
- Windows CUDA/ONNX produces a known cleanup crash on process exit
  AFTER the model file has been written. This script treats those
  specific exit codes as success.
- Each step's output is checked on disk before running; re-runs skip
  already-completed stages.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
WRAPPER = REPO_ROOT / "tools" / "training" / "_train_step_wrapper.py"

# Windows-specific exit codes from CUDA/ONNX cleanup that fire AFTER
# the work has succeeded and the output is on disk.
# 0xC0000409 = STATUS_STACK_BUFFER_OVERRUN
# -1073740791 is the signed-int form of the same.
CLEANUP_CRASH_CODES = {3221226505, -1073740791}


def _safe_filename(phrase: str) -> str:
    s = re.sub(r"[^\w]+", "_", phrase.lower()).strip("_")
    return s or "wakeword"


def _log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    line = "=" * 60
    print(f"\n[{ts}] {line}", flush=True)
    print(f"[{ts}] {msg}", flush=True)
    print(f"[{ts}] {line}", flush=True)


def _run_step(
    config_path: Path,
    step_flag: str,
    work_dir: Path,
    piper_path: Path,
    train_py: Path,
) -> bool:
    """Run one training step via the wrapper. Returns True on success.

    Treats the known Windows CUDA/ONNX cleanup crash as success because
    the actual work (clip generation, feature extraction, model export)
    has already completed and been written to disk by the time the
    crash happens.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = str(piper_path) + os.pathsep + env.get("PYTHONPATH", "")
    # ONNX export prints emoji; Windows cp1252 console can't render them.
    env["PYTHONIOENCODING"] = "utf-8"
    # Wrapper reads these from the environment.
    env["CLARITY_TRAIN_WORK_DIR"] = str(work_dir)
    env["CLARITY_TRAIN_PIPER_PATH"] = str(piper_path)
    env["CLARITY_TRAIN_TRAIN_PY"] = str(train_py)
    env["CLARITY_TRAIN_CONFIG_PATH"] = str(config_path)
    env["CLARITY_TRAIN_STEP_FLAG"] = step_flag

    result = subprocess.run(
        [sys.executable, str(WRAPPER)],
        cwd=str(work_dir),
        env=env,
        timeout=7200,  # 2-hour safety cap per step
    )

    if result.returncode == 0:
        return True
    if result.returncode in CLEANUP_CRASH_CODES:
        print(
            f"  (Known Windows CUDA/ONNX cleanup crash on exit "
            f"{result.returncode} — work completed on disk, continuing.)",
            flush=True,
        )
        return True
    print(
        f"  Step {step_flag} exited with code {result.returncode}",
        flush=True,
    )
    return False


def _build_config(
    target_phrase: str,
    model_name: str,
    piper_path: Path,
    output_dir: Path,
    *,
    n_samples: int,
    n_samples_val: int,
    steps: int,
    layer_size: int,
    augmentation_rounds: int,
    target_accuracy: float,
    target_recall: float,
    target_fp_per_hour: float,
    background_paths: list[Path],
    rir_paths: list[Path],
    feature_data_file: Path,
    validation_features: Path,
) -> dict:
    return {
        "target_phrase": [target_phrase],
        "model_name": model_name,
        "n_samples": n_samples,
        "n_samples_val": n_samples_val,
        "steps": steps,
        "target_accuracy": target_accuracy,
        "target_recall": target_recall,
        "target_false_positives_per_hour": target_fp_per_hour,
        "output_dir": str(output_dir),
        "max_negative_weight": 1500,
        "background_paths": [str(p) for p in background_paths],
        "background_paths_duplication_rate": [1] * len(background_paths),
        "false_positive_validation_data_path": str(validation_features),
        "feature_data_files": {"ACAV100M_sample": str(feature_data_file)},
        "piper_sample_generator_path": str(piper_path),
        "rir_paths": [str(p) for p in rir_paths],
        "batch_n_per_class": {
            "ACAV100M_sample": 1024,
            "adversarial_negative": 50,
            "positive": 50,
        },
        "augmentation_rounds": augmentation_rounds,
        "augmentation_batch_size": 16,
        "layer_size": layer_size,
        "model_type": "dnn",
        "tts_batch_size": 50,
        "custom_negative_phrases": [],
    }


def _stages_to_run(
    model_output_dir: Path,
    n_samples: int,
    n_samples_val: int,
) -> list[tuple[str, str]]:
    """Decide which stages need to run based on what's already on disk.

    Pipeline: generate clips → augment clips → train. Each stage's output
    is detectable; skip the ones already done.
    """
    pos_train = model_output_dir / "positive_train"
    pos_test = model_output_dir / "positive_test"
    clips_exist = (
        pos_train.exists()
        and pos_test.exists()
        and len(list(pos_train.glob("*.wav"))) >= n_samples
        and len(list(pos_test.glob("*.wav"))) >= n_samples_val
    )

    feature_files = [
        "positive_features_train.npy",
        "positive_features_test.npy",
        "negative_features_train.npy",
        "negative_features_test.npy",
    ]
    features_exist = all((model_output_dir / f).exists() for f in feature_files)

    if features_exist:
        return [("--train_model", "Training the model")]
    if clips_exist:
        return [
            ("--augment_clips", "Augmenting clips with noise + reverb"),
            ("--train_model", "Training the model"),
        ]
    return [
        ("--generate_clips", "Generating synthetic audio clips"),
        ("--augment_clips", "Augmenting clips with noise + reverb"),
        ("--train_model", "Training the model"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train a custom wake-word model.",
    )
    parser.add_argument(
        "--phrase",
        required=True,
        help="The wake phrase (e.g., 'cv go').",
    )
    parser.add_argument(
        "--model-name",
        required=True,
        help="Output model name (used for the ONNX filename).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Training data directory containing piper-sample-generator, "
        "openwakeword, mit_rirs, ACAV100M features, background_noise. "
        "Default: ./models/training_data/",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Where to copy the final ONNX. Default: "
        "models/wake_words/<model-name>.onnx",
    )
    parser.add_argument("--n-samples", type=int, default=10000)
    parser.add_argument("--n-samples-val", type=int, default=2000)
    parser.add_argument("--steps", type=int, default=25000)
    parser.add_argument("--layer-size", type=int, default=64)
    parser.add_argument("--augmentation-rounds", type=int, default=2)
    parser.add_argument("--target-accuracy", type=float, default=0.7)
    parser.add_argument("--target-recall", type=float, default=0.5)
    parser.add_argument("--target-fp-per-hour", type=float, default=0.2)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete any existing intermediate output for this model before training.",
    )
    parser.add_argument(
        "--stop-after",
        choices=["generate", "augment"],
        default=None,
        help="Exit after the named stage (lets you inject real-voice "
        "clips into positive_train/positive_test before augmentation).",
    )
    args = parser.parse_args()

    safe = _safe_filename(args.model_name)

    # Resolve data dir.
    data_dir = args.data_dir or (REPO_ROOT / "models" / "training_data")
    if not data_dir.exists():
        print(
            f"[FAIL] Training data directory does not exist: {data_dir}\n"
            "       Pass --data-dir pointing to a populated directory.",
            file=sys.stderr,
        )
        return 1

    piper_path = data_dir / "piper-sample-generator"
    openwakeword_dir = data_dir / "openwakeword"
    train_py = openwakeword_dir / "openwakeword" / "train.py"
    mit_rirs = data_dir / "mit_rirs"
    background = data_dir / "background_noise"
    acav_features = data_dir / "openwakeword_features_ACAV100M_2000_hrs_16bit.npy"
    val_features = data_dir / "validation_set_features.npy"

    missing = [
        p for p in [piper_path, train_py, acav_features, val_features] if not p.exists()
    ]
    if missing:
        print("[FAIL] Required training data is missing:", file=sys.stderr)
        for p in missing:
            print(f"       {p}", file=sys.stderr)
        return 1

    output_dir = data_dir / "my_custom_model"
    output_dir.mkdir(parents=True, exist_ok=True)
    model_output_dir = output_dir / safe

    if args.clean and model_output_dir.exists():
        _log(f"Cleaning prior output: {model_output_dir}")
        shutil.rmtree(model_output_dir)

    config = _build_config(
        target_phrase=args.phrase,
        model_name=safe,
        piper_path=piper_path,
        output_dir=output_dir,
        n_samples=args.n_samples,
        n_samples_val=args.n_samples_val,
        steps=args.steps,
        layer_size=args.layer_size,
        augmentation_rounds=args.augmentation_rounds,
        target_accuracy=args.target_accuracy,
        target_recall=args.target_recall,
        target_fp_per_hour=args.target_fp_per_hour,
        background_paths=[background] if background.exists() else [],
        rir_paths=[mit_rirs] if mit_rirs.exists() else [],
        feature_data_file=acav_features,
        validation_features=val_features,
    )

    import yaml  # lazy: only training venv needs it

    config_path = data_dir / f"{safe}_config.yaml"
    config_path.write_text(yaml.dump(config), encoding="utf-8")
    print(f"  Config: {config_path}", flush=True)

    stages = _stages_to_run(model_output_dir, args.n_samples, args.n_samples_val)

    stop_flag_map = {
        "generate": "--generate_clips",
        "augment": "--augment_clips",
    }
    stop_flag = stop_flag_map.get(args.stop_after) if args.stop_after else None

    _log(f"Training '{args.phrase}' -> {safe}.onnx")
    print(f"  Stages to run: {[s[0] for s in stages]}", flush=True)

    for flag, description in stages:
        _log(description)
        start = time.time()
        ok = _run_step(
            config_path,
            flag,
            data_dir,
            piper_path,
            train_py,
        )
        elapsed = time.time() - start
        if not ok:
            print(f"  Stage failed after {elapsed:.0f}s", flush=True)
            return 1
        print(f"  Stage completed in {elapsed:.0f}s", flush=True)
        if stop_flag and flag == stop_flag:
            print(f"  Stopping after '{args.stop_after}' as requested.")
            return 0

    model_file = output_dir / f"{safe}.onnx"
    data_file = output_dir / f"{safe}.onnx.data"
    if not model_file.exists():
        print(
            f"[FAIL] Expected model not found at {model_file}",
            file=sys.stderr,
        )
        return 1

    dest = args.out or (REPO_ROOT / "models" / "wake_words" / f"{safe}.onnx")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(model_file, dest)
    size_kb = model_file.stat().st_size / 1024
    print(f"\n  ONNX -> {dest} ({size_kb:.1f} KB)", flush=True)
    if data_file.exists():
        dest_data = dest.with_suffix(".onnx.data")
        shutil.copy2(data_file, dest_data)
        print(f"  Data -> {dest_data}", flush=True)

    _log(f"Training complete: {safe}")
    print(
        f"\n  Next: python tools/training/calibrate.py "
        f"--phrase {args.phrase!r} --model {dest}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
