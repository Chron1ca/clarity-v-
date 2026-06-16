"""
Fetch every training dependency train.py reads from disk.

train.py expects six things in ``<data-dir>``:

  * ``piper-sample-generator/``           — synthesizer repo (cloned)
  * ``piper-sample-generator/en_US-libritts_r-medium.pt``  — voice ckpt
  * ``openwakeword/``                     — training-pipeline repo (cloned)
  * ``openwakeword_features_ACAV100M_2000_hrs_16bit.npy``  — ~17 GB
  * ``validation_set_features.npy``       — ~177 MB
  * ``mit_rirs/``                         — room-impulse-response WAVs

This script puts each one in place. Every step is idempotent — re-run
freely; nothing already on disk is re-downloaded. Total: ~17.5 GB.

Usage:
    python tools/training/fetch_negatives.py
    python tools/training/fetch_negatives.py --data-dir D:/path/to/data

After this completes, ``train.py --phrase ... --model-name ...`` runs
end-to-end from a fresh clone (assuming the training-stack venv is set
up per ``tools/training/requirements.txt``).

Notes on URLs:
- Feature .npy files come from the davidscripka/openwakeword_features
  HuggingFace dataset (the openwakeword maintainer's canonical mirror).
- piper-sample-generator releases the voice checkpoint as a GitHub
  release asset.
- openwakeword + piper-sample-generator clones come from their canonical
  GitHub repos. Cloning over HTTPS — no auth required.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

# ─── Canonical sources ────────────────────────────────────────────────

PIPER_SAMPLE_GENERATOR_REPO = "https://github.com/rhasspy/piper-sample-generator"
PIPER_VOICE_CKPT_URL = (
    "https://github.com/rhasspy/piper-sample-generator/releases/download/"
    "v1.0.0/en_US-libritts_r-medium.pt"
)
PIPER_VOICE_CKPT_FILENAME = "en_US-libritts_r-medium.pt"

OPENWAKEWORD_REPO = "https://github.com/dscripka/openWakeWord"

HF_OPENWAKEWORD_FEATURES_REPO = "davidscripka/openwakeword_features"
ACAV_FEATURES_FILENAME = "openwakeword_features_ACAV100M_2000_hrs_16bit.npy"
VALIDATION_FEATURES_FILENAME = "validation_set_features.npy"
MIT_RIRS_FILENAME = "mit_rirs.tar.gz"


# ─── Helpers ──────────────────────────────────────────────────────────


def _log(msg: str) -> None:
    print(f"[fetch_negatives] {msg}", flush=True)


def _run(cmd: list[str], cwd: Path | None = None) -> bool:
    """Run a subprocess; True on exit 0, False otherwise."""
    _log(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
    return result.returncode == 0


# ─── Steps ────────────────────────────────────────────────────────────


def step_clone_piper_sample_generator(data_dir: Path) -> bool:
    """Clone piper-sample-generator unless the directory already exists."""
    target = data_dir / "piper-sample-generator"
    if target.exists() and any(target.iterdir()):
        _log(f"piper-sample-generator/ already present at {target} — skip")
        return True
    _log(f"Cloning piper-sample-generator into {target}")
    return _run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            PIPER_SAMPLE_GENERATOR_REPO,
            str(target),
        ]
    )


def step_download_piper_voice(data_dir: Path) -> bool:
    """Download the en_US-libritts_r-medium.pt voice checkpoint."""
    target = data_dir / "piper-sample-generator" / PIPER_VOICE_CKPT_FILENAME
    if target.exists() and target.stat().st_size > 0:
        _log(f"Piper voice checkpoint already present at {target} — skip")
        return True
    if not target.parent.exists():
        _log(
            f"[FAIL] {target.parent} does not exist — clone "
            f"piper-sample-generator first."
        )
        return False
    return _download_with_resume(PIPER_VOICE_CKPT_URL, target)


def step_clone_openwakeword(data_dir: Path) -> bool:
    """Clone openwakeword unless the directory already exists."""
    target = data_dir / "openwakeword"
    if target.exists() and any(target.iterdir()):
        _log(f"openwakeword/ already present at {target} — skip")
        return True
    _log(f"Cloning openwakeword into {target}")
    return _run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            OPENWAKEWORD_REPO,
            str(target),
        ]
    )


def step_download_acav_features(data_dir: Path) -> bool:
    """Download the ACAV100M feature .npy (~17 GB)."""
    return _hf_download(
        repo_id=HF_OPENWAKEWORD_FEATURES_REPO,
        filename=ACAV_FEATURES_FILENAME,
        target_dir=data_dir,
        label="ACAV100M features",
    )


def step_download_validation_features(data_dir: Path) -> bool:
    """Download the validation feature .npy (~177 MB)."""
    return _hf_download(
        repo_id=HF_OPENWAKEWORD_FEATURES_REPO,
        filename=VALIDATION_FEATURES_FILENAME,
        target_dir=data_dir,
        label="validation features",
    )


def step_download_mit_rirs(data_dir: Path) -> bool:
    """Download + extract the MIT room-impulse-response set."""
    target_dir = data_dir / "mit_rirs"
    if target_dir.exists() and any(target_dir.glob("*.wav")):
        _log(f"mit_rirs/ already populated at {target_dir} — skip")
        return True

    archive = data_dir / MIT_RIRS_FILENAME
    if not (archive.exists() and archive.stat().st_size > 0):
        ok = _hf_download(
            repo_id=HF_OPENWAKEWORD_FEATURES_REPO,
            filename=MIT_RIRS_FILENAME,
            target_dir=data_dir,
            label="MIT RIRs archive",
        )
        if not ok:
            return False

    _log(f"Extracting {archive} -> {target_dir}")
    import tarfile

    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(target_dir)
    except (OSError, tarfile.TarError) as e:
        _log(f"[FAIL] Could not extract {archive}: {e}")
        return False
    return True


# ─── Download primitives ──────────────────────────────────────────────


def _hf_download(
    repo_id: str,
    filename: str,
    target_dir: Path,
    label: str,
) -> bool:
    """Download via huggingface_hub.hf_hub_download into target_dir/filename.

    Idempotent: if the file is already present at the destination with
    non-zero size, the download is skipped. hf_hub_download itself caches
    + supports resume.
    """
    target = target_dir / filename
    if target.exists() and target.stat().st_size > 0:
        _log(f"{label} already present at {target} — skip")
        return True
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        _log(
            "[FAIL] huggingface_hub not installed. Install with: "
            "pip install huggingface-hub"
        )
        return False
    _log(f"Downloading {label} from HF {repo_id}/{filename}")
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        downloaded = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            repo_type="dataset",
            local_dir=str(target_dir),
        )
    except Exception as e:
        _log(f"[FAIL] HF download {label}: {type(e).__name__}: {e}")
        return False
    # Some hf_hub_download versions resolve into a cache subdir; move/copy
    # into the expected location if so.
    downloaded_path = Path(downloaded)
    if downloaded_path != target and downloaded_path.exists():
        try:
            import shutil

            shutil.copy2(downloaded_path, target)
        except OSError as e:
            _log(f"[FAIL] Could not place {label} at {target}: {e}")
            return False
    _log(f"{label} ready at {target}")
    return True


def _download_with_resume(url: str, dest: Path) -> bool:
    """HTTP download with Range-resume; idempotent on exit 0 file."""
    try:
        import requests
    except ImportError:
        _log("[FAIL] requests not installed. pip install requests")
        return False
    try:
        from tqdm import tqdm
    except ImportError:
        tqdm = None  # type: ignore

    headers: dict = {}
    resume_at = 0
    if dest.exists():
        resume_at = dest.stat().st_size
        headers["Range"] = f"bytes={resume_at}-"

    try:
        with requests.get(url, stream=True, headers=headers, timeout=60) as r:
            if r.status_code == 416:
                _log(f"Already complete: {dest.name}")
                return True
            if r.status_code not in (200, 206):
                _log(f"[FAIL] HTTP {r.status_code}: {url}")
                return False
            total = int(r.headers.get("Content-Length", 0))
            if r.status_code == 200:
                resume_at = 0
                total_full = total
            else:
                total_full = total + resume_at
            mode = "ab" if r.status_code == 206 else "wb"
            bar = None
            if tqdm:
                bar = tqdm(
                    total=total_full,
                    initial=resume_at,
                    unit="B",
                    unit_scale=True,
                    desc=dest.name,
                )
            with open(dest, mode) as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        if bar:
                            bar.update(len(chunk))
            if bar:
                bar.close()
        return True
    except Exception as e:
        _log(f"[FAIL] Download {url}: {type(e).__name__}: {e}")
        return False


# ─── Orchestration ────────────────────────────────────────────────────


STEPS = [
    ("Clone piper-sample-generator", step_clone_piper_sample_generator),
    ("Download Piper voice checkpoint", step_download_piper_voice),
    ("Clone openwakeword", step_clone_openwakeword),
    ("Download validation features (.npy, ~177 MB)", step_download_validation_features),
    ("Download MIT RIRs", step_download_mit_rirs),
    # ACAV100M last because it's the giant 17 GB download — fail fast on
    # cheap steps before sinking hours into bandwidth.
    ("Download ACAV100M features (.npy, ~17 GB)", step_download_acav_features),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=("Fetch every training dependency train.py reads from disk."),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Where to place training data. Default: "
        "<repo>/models/training_data/. Must match the --data-dir you'll "
        "pass to train.py.",
    )
    args = parser.parse_args()

    data_dir = args.data_dir or (REPO_ROOT / "models" / "training_data")
    data_dir.mkdir(parents=True, exist_ok=True)
    _log(f"Training data root: {data_dir.resolve()}")
    _log("Total download size on a cold cache: ~17.5 GB")
    _log("Re-runs skip what's already on disk.")
    print()

    failed: list[str] = []
    for label, step_fn in STEPS:
        _log(f"--- {label} ---")
        ok = step_fn(data_dir)
        if not ok:
            failed.append(label)
            _log(f"[FAIL] {label} — continuing with remaining steps")
        print()

    print()
    if failed:
        _log(f"{len(failed)} step(s) failed:")
        for f in failed:
            _log(f"  - {f}")
        _log("Re-run after fixing the cause (network, disk, etc.).")
        return 1
    _log("All training dependencies in place.")
    _log(f"  Data dir: {data_dir.resolve()}")
    _log("Next: tools/training/generate_samples.py, then train.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
