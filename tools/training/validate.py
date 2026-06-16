"""
Validate a trained wake-word model against your own voice + normal speech.

Two stages:
  1. Detection test — say the phrase 10 times. Detection rate should
     be 9/10 or 10/10. If lower, the model under-fits to your voice
     (record more personal samples, retrain).
  2. False-positive test — talk normally for 30 s WITHOUT saying the
     phrase. Detector should not fire. If it does, the model is too
     sensitive (raise threshold, or add hard-negative samples and retrain).

If both pass, the script offers to install the model: copies it to
`models/wake_words/` and updates `wake_config.json` to use it.

Usage:
    python tools/training/validate.py \\
        --phrase "cv go" --model models/wake_words/cv_go.onnx
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import sounddevice as sd


REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


SAMPLE_RATE = 16000
BLOCKSIZE = 4000


def _capture(seconds: float) -> list:
    """Capture `seconds` of audio and return list of int16 chunks."""
    chunks = []

    def cb(indata, frames, time_info, status):
        chunks.append(indata.copy().flatten())

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=BLOCKSIZE,
        callback=cb,
    ):
        time.sleep(seconds)
    return chunks


def _run_model_on_chunks(chunks, model_path: Path, threshold: float) -> int:
    """Feed chunks to the wake detector; return number of detections."""
    from clarity_v.wake import WakeDetector

    name = model_path.stem
    config = {
        "models": [
            {"name": name, "model_path": str(model_path), "threshold": threshold},
        ],
        "cooldown_seconds": 0.3,
    }
    detector = WakeDetector(config)
    if not detector.enabled:
        print("[FAIL] Detector did not load the model.")
        return -1
    detections = 0
    for chunk in chunks:
        evt = detector.feed(chunk)
        if evt:
            detections += 1
            print(f"  [DETECT] {evt.model} score={evt.score:.3f}")
    return detections


def stage_detection_rate(phrase: str, model_path: Path, threshold: float) -> bool:
    """Stage 1: say the phrase 10 times, count detections."""
    print("\n=== Stage 1: Detection rate ===")
    print(f"You'll be prompted 10 times to say {phrase!r}. Speak naturally.")
    input("Press Enter to start...")
    hits = 0
    for i in range(1, 11):
        print(f"\nTake {i}/10 — say {phrase!r}")
        for c in range(3, 0, -1):
            print(f"  {c}...")
            time.sleep(0.5)
        print("  RECORDING (2s)")
        chunks = _capture(2.0)
        detected = _run_model_on_chunks(chunks, model_path, threshold)
        if detected < 0:
            return False
        if detected >= 1:
            hits += 1
            print("  [OK]   detected")
        else:
            print("  [FAIL] not detected")
    print(f"\nDetection rate: {hits}/10")
    if hits >= 8:
        print("OK (>= 8/10)")
        return True
    print(
        "FAIL (< 8/10) — model under-fits your voice. "
        "Record more personal samples + retrain."
    )
    return False


def stage_false_positives(model_path: Path, threshold: float) -> bool:
    """Stage 2: talk normally for 30 s without the wake phrase."""
    print("\n=== Stage 2: False-positive rate ===")
    print("Now talk naturally for 30 seconds — read aloud, narrate, hum,")
    print("anything EXCEPT the wake phrase.")
    input("Press Enter to start...")
    print("Recording 30 s of normal speech...")
    chunks = _capture(30.0)
    detections = _run_model_on_chunks(chunks, model_path, threshold)
    if detections < 0:
        return False
    print(f"\nFalse positives in 30 s: {detections}")
    if detections == 0:
        print("OK (0 false positives)")
        return True
    if detections <= 1:
        print("MARGINAL (1 false positive) — usable but consider raising threshold.")
        return True
    print(
        f"FAIL (>{detections} false positives) — model too sensitive. "
        "Raise threshold or add hard negatives + retrain."
    )
    return False


def _infer_role_from_name(name: str) -> str:
    """Infer wake-word role from naming convention.

    Names ending in/containing ``over``/``stop``/``end`` → ``"stop"`` (the
    wake fires to END dictation). Anything else → ``"start"`` (the wake
    fires to BEGIN dictation). Same convention as
    ``tools/training/calibrate.py``.
    """
    lowered = name.lower()
    if any(suffix in lowered for suffix in ("over", "stop", "end")):
        return "stop"
    return "start"


def deploy(
    model_path: Path,
    phrase: str,
    threshold: float = 0.5,
    *,
    repo_root: Path | None = None,
    config_path: Path | None = None,
) -> bool:
    """Install a validated model and merge it into ``wake_config.json``.

    Reads the existing config first, preserves every entry, then merges
    the new model by name — updating threshold + role on an existing
    entry, or appending a new one. Never destroys other entries.
    ``cooldown_seconds`` is preserved from the existing config (defaults
    to 0.5 when bootstrapping a fresh config).

    Args:
        model_path: Path to the trained .onnx file to install.
        phrase: The wake phrase. Kept for parity with the rest of the
            tooling; ``wake_config.json`` only stores name/model_path/
            threshold/role so it isn't written to disk.
        threshold: Threshold to write. Pass the value that passed
            validation, not a hard-coded default.
        repo_root: Override the deployment root (used by tests). Defaults
            to the actual repo root.
        config_path: Override the config path (used by tests). Defaults
            to ``<repo_root>/wake_config.json``.

    Returns:
        True on success.
    """
    rr = repo_root or REPO_ROOT
    cfg = config_path or (rr / "wake_config.json")

    # 1. Copy the model into the wake-words directory.
    target_dir = rr / "models" / "wake_words"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / model_path.name
    shutil.copy(model_path, target_path)
    print(f"Copied model to: {target_path}")

    # 2. Read existing config. Bootstrap fresh if file is missing or
    # malformed; never crash on a corrupt config — overwrite cleanly.
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}

    existing_models = data.get("models")
    if not isinstance(existing_models, list):
        existing_models = []
    cooldown = data.get("cooldown_seconds", 0.5)

    name = model_path.stem
    role = _infer_role_from_name(name)
    # Forward-slash path: wake_config.json is consumed cross-platform,
    # never serialize Windows backslashes (they break on Linux/Mac
    # readers and clash with the existing config convention).
    new_entry = {
        "name": name,
        "model_path": target_path.relative_to(rr).as_posix(),
        "threshold": round(float(threshold), 3),
        "role": role,
    }

    # 3. Merge by name: replace an existing entry, or append a new one.
    merged: list = []
    found = False
    for entry in existing_models:
        if isinstance(entry, dict) and entry.get("name") == name:
            merged.append(new_entry)
            found = True
        else:
            merged.append(entry)
    if not found:
        merged.append(new_entry)

    data["models"] = merged
    data["cooldown_seconds"] = cooldown

    cfg.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Updated config: {cfg}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a trained wake-word model.")
    parser.add_argument("--phrase", required=True, help="The wake phrase.")
    parser.add_argument(
        "--model", type=Path, required=True, help="Path to the .onnx model."
    )
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument(
        "--no-deploy",
        action="store_true",
        help="Don't deploy even if both stages pass.",
    )
    args = parser.parse_args()

    if not args.model.exists():
        print(f"[FAIL] Model not found: {args.model}")
        return 1

    s1 = stage_detection_rate(args.phrase, args.model, args.threshold)
    s2 = stage_false_positives(args.model, args.threshold)

    print("\n" + "=" * 50)
    print(f"Stage 1 (detection): {'OK' if s1 else 'FAIL'}")
    print(f"Stage 2 (false-pos): {'OK' if s2 else 'FAIL'}")
    print("=" * 50)

    if s1 and s2 and not args.no_deploy:
        ans = input("\nDeploy this model? [y/n]: ")
        if ans.strip().lower() == "y":
            deploy(args.model, args.phrase, threshold=args.threshold)
            print("\nDone. Restart Clarity.V to use the new model.")
            return 0

    if s1 and s2:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
