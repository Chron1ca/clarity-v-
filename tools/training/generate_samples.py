"""
Generate synthetic positive samples for ANY custom wake word.

Train your own wake phrase — not just the bundled defaults. Run with
--phrase "my custom word" and the script produces thousands of
synthetic utterances of that phrase using diverse TTS voices, accents,
rates, and pitches.

Strategy:
- Microsoft Edge TTS (edge-tts, free, no API key) — 50+ voices across
  English variants (US, UK, AU, CA, IN, IE, NZ, ZA, NG, KE, PH, SG, HK)
  plus Portuguese, Spanish, French, German, Italian for robustness
  against false-positive firing on other languages.
- Multiple phrasings derived from your input (with/without punctuation,
  greetings prepended, "please" appended, etc.).
- Rate variations: -25%, -15%, -10%, 0, +10%, +15%, +25% — captures fast
  + slow speakers.
- Pitch variations: -10 Hz to +10 Hz — captures higher and lower voices.

Default targets 5000 samples — the practical floor for a usable model.
More is better: 10000+ recommended for production-quality wake words.

Usage:
    python tools/training/generate_samples.py \\
        --phrase "cv go" --model-name cv_go --target 5000

    python tools/training/generate_samples.py \\
        --phrase "computer" --model-name computer --target 8000

Samples land in:
    <data-dir>/my_custom_model/<model-name>/positive_train/   (80%)
    <data-dir>/my_custom_model/<model-name>/positive_test/    (20%)

This matches the layout train.py reads — same --model-name + --data-dir
flags chain through the whole training pipeline.

Requirements:
    pip install edge-tts
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import random
import re
import sys
from itertools import product
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


# ─── Voice catalog ────────────────────────────────────────────────────

# Diverse set of Edge TTS voices across accents and a few languages.
# More languages = more robust to false-positive firing on non-English
# audio. Full list: `edge-tts --list-voices`.
VOICES = [
    # English — US (various)
    "en-US-AriaNeural",
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-US-AnaNeural",
    "en-US-ChristopherNeural",
    "en-US-EricNeural",
    "en-US-MichelleNeural",
    "en-US-RogerNeural",
    "en-US-SteffanNeural",
    # English — UK
    "en-GB-LibbyNeural",
    "en-GB-RyanNeural",
    "en-GB-SoniaNeural",
    "en-GB-MaisieNeural",
    "en-GB-ThomasNeural",
    # English — Other accents
    "en-AU-NatashaNeural",
    "en-AU-WilliamNeural",
    "en-CA-ClaraNeural",
    "en-CA-LiamNeural",
    "en-IE-EmilyNeural",
    "en-IE-ConnorNeural",
    "en-IN-NeerjaNeural",
    "en-IN-PrabhatNeural",
    "en-NZ-MollyNeural",
    "en-NZ-MitchellNeural",
    "en-ZA-LeahNeural",
    "en-ZA-LukeNeural",
    "en-NG-EzinneNeural",
    "en-NG-AbeoNeural",
    "en-KE-AsiliaNeural",
    "en-KE-ChilembaNeural",
    "en-PH-RosaNeural",
    "en-PH-JamesNeural",
    "en-SG-LunaNeural",
    "en-SG-WayneNeural",
    "en-HK-YanNeural",
    "en-HK-SamNeural",
    # Portuguese
    "pt-PT-DuarteNeural",
    "pt-PT-RaquelNeural",
    "pt-BR-FranciscaNeural",
    "pt-BR-AntonioNeural",
    "pt-BR-BrendaNeural",
    "pt-BR-DonatoNeural",
    # Other languages (robustness)
    "es-ES-ElviraNeural",
    "es-ES-AlvaroNeural",
    "fr-FR-DeniseNeural",
    "fr-FR-HenriNeural",
    "de-DE-KatjaNeural",
    "de-DE-ConradNeural",
    "it-IT-ElsaNeural",
    "it-IT-DiegoNeural",
]

RATES = ["-25%", "-15%", "-10%", "+0%", "+10%", "+15%", "+25%"]
PITCHES = ["-10Hz", "-5Hz", "+0Hz", "+5Hz", "+10Hz"]


def _build_phrasings(phrase: str) -> list[str]:
    """Build phrasing variations from a base wake phrase.

    Variations cover natural prosody differences. Edge TTS reads
    punctuation cues for tempo/stress, so adding commas/question
    marks/exclamation points produces meaningfully different audio.
    """
    p = phrase.strip()
    if not p:
        raise ValueError("--phrase cannot be empty")

    # Capitalized variants
    cap = " ".join(w.capitalize() for w in p.split())
    upper_first = p[0].upper() + p[1:] if len(p) > 1 else p.upper()

    variations = {
        p,
        upper_first,
        cap,
        f"{p}.",
        f"{p}!",
        f"{p}?",
        f"{cap}.",
        f"{cap}!",
        f"{upper_first}!",
        f"hey {p}",
        f"hey, {p}",
        f"hi {p}",
        f"okay {p}",
        f"{p} please",
        f"yo {p}",
    }
    return sorted(variations)


def _safe_filename(phrase: str) -> str:
    """Sanitize a phrase into a filesystem-safe directory name."""
    s = re.sub(r"[^\w]+", "_", phrase.lower()).strip("_")
    return s or "wakeword"


# ─── Generation ───────────────────────────────────────────────────────


async def _generate_one(text, voice, rate, pitch, out_path):
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_path))


async def _generate_batch(jobs, concurrency: int):
    semaphore = asyncio.Semaphore(concurrency)
    failures = 0
    completed = 0

    async def _bounded(job):
        nonlocal failures, completed
        text, voice, rate, pitch, out_path, idx = job
        async with semaphore:
            try:
                await _generate_one(text, voice, rate, pitch, out_path)
                # Edge TTS sometimes "succeeds" but writes an empty/tiny
                # file. Treat anything < 1 KB as a failure.
                if out_path.exists() and out_path.stat().st_size < 1024:
                    out_path.unlink()
                    raise RuntimeError("output file is empty (TTS no-audio)")
                completed += 1
                if completed % 100 == 0:
                    print(
                        f"  [{completed:5d}] {voice:32s} {rate:>5s} "
                        f'{pitch:>6s} "{text}"'
                    )
            except Exception as e:
                failures += 1
                # Clean up the empty file so resume reruns this job.
                if out_path.exists():
                    with contextlib.suppress(OSError):
                        out_path.unlink()
                if failures < 10:
                    print(f"  [FAIL] {voice} {rate} {pitch}: {e}")

    await asyncio.gather(*(_bounded(j) for j in jobs))
    if failures:
        print(f"\n  {failures} generation failures (rate-limited / network)")
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic samples for any custom wake word."
    )
    parser.add_argument(
        "--phrase",
        required=True,
        help="The wake phrase to train (e.g., 'cv go').",
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
        "--target",
        type=int,
        default=5000,
        help="Number of samples to generate (default 5000).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Concurrent TTS requests (default 8).",
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("[FAIL] edge-tts not installed. Install with: pip install edge-tts")
        return 1

    phrasings = _build_phrasings(args.phrase)
    safe_name = _safe_filename(args.model_name or args.phrase)
    data_dir = args.data_dir or (REPO_ROOT / "models" / "training_data")
    model_root = data_dir / "my_custom_model" / safe_name
    train_dir = model_root / "positive_train"
    test_dir = model_root / "positive_test"
    train_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    total_combos = len(phrasings) * len(VOICES) * len(RATES) * len(PITCHES)
    target = min(args.target, total_combos)
    print(f"Wake phrase:  {args.phrase!r}")
    print(f"Model name:   {safe_name!r}")
    print(f"Phrasings:    {len(phrasings)} (e.g. {phrasings[:3]})")
    print(f"Voices:       {len(VOICES)}")
    print(f"Rates:        {len(RATES)}")
    print(f"Pitches:      {len(PITCHES)}")
    print(f"Combinations: {total_combos}")
    print(f"Target:       {target}")
    print(f"Output train: {train_dir.resolve()}")
    print(f"Output test:  {test_dir.resolve()}")
    print()

    all_combos = list(product(phrasings, VOICES, RATES, PITCHES))
    random.seed(args.seed)
    random.shuffle(all_combos)
    chosen = all_combos[:target]

    # 80/20 split: every 5th sample (1-indexed) lands in positive_test,
    # the rest in positive_train. Same pattern as import_real_clips.py
    # so the full training data set behaves uniformly.
    jobs = []
    for idx, (text, voice, rate, pitch) in enumerate(chosen):
        target_dir = test_dir if (idx + 1) % 5 == 0 else train_dir
        out_path = target_dir / f"{safe_name}_{idx:05d}.wav"
        if out_path.exists():
            continue
        jobs.append((text, voice, rate, pitch, out_path, idx))

    if not jobs:
        print("All target samples already exist. Nothing to do.")
        return 0

    print(f"Generating {len(jobs)} samples (concurrency={args.concurrency})...")
    completed = asyncio.run(_generate_batch(jobs, args.concurrency))

    on_disk_train = sum(1 for _ in train_dir.glob(f"{safe_name}_*.wav"))
    on_disk_test = sum(1 for _ in test_dir.glob(f"{safe_name}_*.wav"))
    print(
        f"\nDone. {on_disk_train} train + {on_disk_test} test samples in {model_root}"
    )
    print(
        f"Generated this run: {completed}; "
        f"total on disk: {on_disk_train + on_disk_test}"
    )
    print(
        f"\nNext: python tools/training/train.py --phrase {args.phrase!r} "
        f"--model-name {safe_name}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
