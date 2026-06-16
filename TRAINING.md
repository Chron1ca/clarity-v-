# Training your own wake word

This guide explains how to train Clarity.V to listen for a wake phrase you choose, optionally adapted to your own voice. The result is a small `.onnx` file that Clarity.V loads at startup.

**You don't need to be an ML person.** The easiest way to train a new wake word is to use the automated wizard:
1. Open the Clarity.V Settings window.
2. Go to the **Voice Activation** tab.
3. Click **Train New Wake Word** or **Enhance** on an existing wake word.
This displays a warning dialog informing you about the 17.5 GB training data requirements. Once confirmed, it launches a detached console that automates the environment setup and walks you through every step below interactively.

> **If you're an AI agent or a developer:** The wizard (`tools/training/wizard.py`) automates the manual CLI pipeline documented below. The CLI steps remain available for advanced usage, scripting, or debugging.

## What ships out-of-the-box

Clarity.V ships with **two** trained wake words by default, so most Persons never need to read this guide:

- **`cv_go`** — role `start`, default threshold `0.5`. Fires on `"see vee go"` to begin dictation.
- **`cv_over`** — role `stop`, default threshold `0.35`. Fires on `"see vee over"` to end dictation.

Both are calibrated against the author's voice in the repo (see [wake_config.json](wake_config.json)); downstream users keep the conservative defaults until they recalibrate.

This guide is for: training an additional / replacement wake word in your own voice, in your own room, with your own mic.

---

## What you get when you finish

A trained ONNX file at `models/wake_words/<model-name>.onnx`, a calibrated entry merged into `wake_config.json`, and a wake word that fires on you and stays quiet otherwise.

---

## Prerequisites

```bash
pip install -r requirements.txt
pip install -r tools/training/requirements.txt
```

The second file pulls in the heavier ML stack (PyTorch, librosa, edge-tts, openwakeword's training deps). It's separate from the runtime requirements so users who don't train wake words don't pay the install cost.

You also need:

- **A microphone**, for the personal-voice and calibration steps.
- **~17.5 GB of disk space** for the openwakeword feature dataset, validation set, MIT room impulse responses, and the Piper voice checkpoint.
- **A CUDA GPU is strongly recommended.** ~15 minutes per model on a 5090 with the defaults below. CPU-only is hours.

Clarity.V's runtime venv doesn't include the training stack. Create a separate venv for training to avoid version conflicts:

```bash
python -m venv .venv-train
.venv-train\Scripts\activate          # Windows
# source .venv-train/bin/activate     # macOS/Linux
pip install -r tools/training/requirements.txt
```

---

## Step 1 — Pick your wake phrase and model name

Good wake phrases share these traits:

- **2–4 syllables.** Short ones produce too many false positives; long ones are annoying.
- **Distinctive sounds.** Avoid phrases that sound like common English words you might say casually. `"hey computer"` is fine; `"the way to"` would fire constantly.
- **Easy to say repeatedly.** You'll say this dozens of times an hour.

Examples that work well: `"cv go"`, `"hey jarvis"`, `"okay computer"`, `"yo cortana"`.

You'll also pick a **model name** — a short snake_case identifier for the trained `.onnx` file and the directory the training pipeline creates. The model name flows through every step via `--model-name`. Pick something short and ASCII-safe.

> **AI agent:** ask the Person what phrase they want and what they want to call it. If their suggestion is one syllable or sounds like common speech, recommend an alternative and let them confirm. If they say "you pick the name," derive a `snake_case` name from the phrase: e.g. `"okay computer"` → `okay_computer`.

This guide uses `cv_go` as the running example.

---

## Step 2 — Fetch the training dependencies

The trainer needs precomputed feature files, a TTS voice checkpoint, and the openwakeword + piper-sample-generator source. One command pulls them all:

```bash
python tools/training/fetch_negatives.py
```

What it places under `models/training_data/`:

- `piper-sample-generator/` and the `en_US-libritts_r-medium.pt` voice checkpoint (synthetic-sample TTS).
- `openwakeword/` (the training pipeline source).
- `openwakeword_features_ACAV100M_2000_hrs_16bit.npy` — ~17 GB of precomputed negative features.
- `validation_set_features.npy` — ~177 MB of validation features.
- `mit_rirs/` — room impulse responses for augmentation.

Total ~17.5 GB on a cold cache; re-runs skip what's already on disk. Pass `--data-dir D:/path/to/data` to put everything somewhere else (just remember to use the same `--data-dir` for every script below).

---

## Step 3 — Generate synthetic positive samples

This makes ~5000+ varied WAVs of your phrase using many different TTS voices, accents, speeds, and pitches. No mic required.

```bash
python tools/training/generate_samples.py \
    --phrase "cv go" --model-name cv_go --target 5000
```

Samples land in an 80/20 train/test split:

- `models/training_data/my_custom_model/cv_go/positive_train/` (80%)
- `models/training_data/my_custom_model/cv_go/positive_test/`  (20%)

Takes 10–30 minutes depending on network speed (uses Microsoft's free Edge TTS endpoint). The script supports resume: re-running picks up where it left off.

For a robust model, target 5000+. For experimentation, 1000 is enough to see the system work. For production-quality, 10000+.

---

## Step 4 (strongly recommended) — Record your own voice

Synthetic samples cover voice variety in general, but not *your* voice in *your* room with *your* microphone. Adding 20–30 personal recordings (augmented to ~500 samples) dramatically improves accuracy for you specifically.

```bash
python tools/training/record_personal_voice.py \
    --phrase "cv go" --model-name cv_go --takes 25
```

The script will prompt you to say the phrase 25 times. Each take:

1. 3-second countdown.
2. 2-second recording window.
3. Auto-trims silence around your speech.
4. Generates 20 augmented variants (pitch shift, time stretch, light noise).

Personal takes use the same 80/20 split as Step 3 and land in the same `positive_train/` + `positive_test/` directories, prefixed `personal_*`.

Tips:

- Speak naturally — the way you'll actually use it.
- **Vary across takes.** Louder/softer, faster/slower, closer/farther from the mic, different angles. Variety is what teaches the model robustness.
- Don't try to "sound the same" each take. The opposite.

> **AI agent:** read the on-screen prompts to the Person and confirm each take captured. If a take is "Too short, skipped" — ask the Person to speak louder or move closer to the mic.

---

## Step 5 (optional) — Inject longer-form recordings

Already have a long voice memo where you say the phrase many times naturally? Skip the recording loop in Step 4 and let this script chop it into training clips:

```bash
python tools/training/import_real_clips.py \
    --source path/to/voice_memo.m4a --model-name cv_go
```

Same output layout as Steps 3 and 4. Requires `ffmpeg` on PATH. Detects utterances via per-frame RMS energy; pads or center-crops each to 2.0 s; writes them into `positive_train/` and `positive_test/` (80/20).

---

## Step 6 — Train the model

The trainer wraps openwakeword's training pipeline with Windows-CUDA compatibility shims:

```bash
python tools/training/train.py --phrase "cv go" --model-name cv_go
```

What happens:

1. Builds a training config from your phrase and model name.
2. Detects which stages already ran on disk and skips them (so re-runs don't redo the hours-long sample-generation if you already have clips).
3. Generates ~10000 synthetic clips (if Step 3 didn't already), augments them with room impulse responses + noise, then trains a small neural net to discriminate positive from negative for 25000 steps.
4. Exports the best checkpoint to `models/wake_words/cv_go.onnx`.

Defaults that work: `--n-samples 10000 --steps 25000 --layer-size 64 --augmentation-rounds 2`. Override any of them via the corresponding flag.

**On a CUDA GPU (e.g., 5090)**: ~15 minutes per model with the defaults.
**On CPU**: 6–12 hours.

Known Windows quirk: CUDA/ONNX may print a stack-buffer-overrun on process exit AFTER the model has been written to disk. The wrapper treats that specific exit code as success.

> **AI agent:** watch for `[FAIL]` lines or stages exiting with codes other than 0 or 3221226505. If the run plateaus with low accuracy, suggest the Person record more personal samples (Step 4) or raise `--n-samples`.

---

## Step 7 — Calibrate the threshold

A trained model emits a confidence score per audio chunk. The threshold decides when "above this = fire." A one-size-fits-all default works in theory; in practice, your voice + your mic + your room produce a specific score distribution that a calibrated threshold catches cleanly.

```bash
python tools/training/calibrate.py \
    --phrase "cv go" --model models/wake_words/cv_go.onnx
```

The script:

1. Records you saying the phrase 5 times (positive samples).
2. Records 10 seconds of you talking normally (negative samples).
3. Detects mistimed takes and drops them automatically (a take that scores < 10% of the median is treated as an outlier).
4. Reports the separation between your positive scores and the noise floor.
5. Picks a threshold midway between the two and merges it into `wake_config.json`.

Verdicts:

- **GOOD** — clean separation; the calibrated threshold lands between positives and negatives.
- **PARTIAL** — some positives overlap with negatives. The model will miss some detections. More personal samples + retrain.
- **POOR** — negatives match or exceed positives. The model isn't usable. Re-train with more data.

> **AI agent:** if calibration reports PARTIAL or POOR, do NOT skip ahead to validation. Tell the Person which earlier step to redo.

---

## Step 8 — Validate against your voice

Before trusting the model in real use, run a deterministic check that it fires reliably on you and stays quiet otherwise.

```bash
python tools/training/validate.py \
    --phrase "cv go" --model models/wake_words/cv_go.onnx
```

The script:

1. Prompts you to say the phrase 10 times. Reports detection rate (should be 8+/10).
2. Prompts you to talk normally for 30 seconds, NOT saying the phrase. Reports false-positive count (should be 0–1).
3. If both pass, offers to deploy: copies the `.onnx` into `models/wake_words/` and **merges** an entry into `wake_config.json`. Existing entries (e.g., `cv_go` + `cv_over`) are preserved; deploying never destroys other wake words.

If detection rate < 80% or false positives > 1 in 30 s:

- Record more personal samples (Step 4 with more takes).
- Generate more synthetic samples (Step 3 with higher `--target`).
- Re-train (Step 6).

> **AI agent:** if validation fails, do NOT deploy the model. Tell the Person which step to redo and walk them back through it.

---

## Step 9 — Use your model

Restart Clarity.V. The log line at startup should read:

```text
[WakeDetector] Loaded: 'cv_go' (threshold 0.472)
```

Say your wake phrase. The recording state should activate (you'll see the glow bar change color if presence is enabled).

If false positives are common in daily use, raise the threshold in `wake_config.json` (try +0.05 increments). If your phrase doesn't fire reliably, lower it.

---

## Start wakes and stop wakes — the `role` field

Each entry in `wake_config.json` has a `role`:

```json
{
  "name": "cv_go",
  "model_path": "models/wake_words/cv_go.onnx",
  "threshold": 0.472,
  "role": "start"
}
```

Two roles:

- `start` — Idle → Recording (begins dictation). The default for unmarked models.
- `stop` — Recording → Processing (ends dictation cleanly, no silence wait).

Stop-wakes ARE the default end signal — you say `cv_over` to stop, the engine ends recording immediately. The engine does not auto-end on silence (that's opt-in). The default ships both: `cv_go` (start) + `cv_over` (stop).

When you deploy via `validate.py`, the role is inferred from the model name — names containing `over`, `stop`, or `end` become `role=stop`; everything else is `role=start`. Pick a model name that signals the role (e.g. `bedtime_over` for a stop-wake) and the inference does the right thing.

You can edit `wake_config.json` directly to adjust roles if needed.

---

## Sharing your model

The trained `.onnx` is just a file. You can:

- Share it with friends — anyone who wants the same wake phrase, especially if their voice is similar to yours.
- Open a PR adding it to the [community wake words](https://github.com/Chron1ca/clarity-v-community-wake-words) repo (planned).
- Keep it private.

If you share, mention in your release notes:

- The phrase
- Model name and role (`start` / `stop`)
- Number of positive samples (synthetic + personal)
- Validation detection rate + false-positive count
- Languages of TTS voices used (affects which non-English speakers it works for)

---

## Troubleshooting

**`edge-tts` errors during sample generation** — Edge TTS rate-limits. Reduce `--concurrency` (try 4 or 2). The script resumes; just re-run after a few minutes.

**Training out-of-memory on GPU** — Lower `--n-samples` (e.g. `--n-samples 5000`) or reduce `--augmentation-rounds`.

**Validation shows false positives during normal speech** — Your phrase is too close to common words. Either pick a different phrase, or generate more "hard negative" samples (other words that sound similar) and retrain.

**Model doesn't fire on your voice but fires on others** — Insufficient personal samples. Re-do Step 4 with more takes (40+), then re-train.

**Training script fails to import** — Use the dedicated training venv (Prerequisites section). The runtime venv has version conflicts with the training stack.

**Windows CUDA cleanup crash on training exit** — Known quirk; `train.py` recognizes the specific exit code (`3221226505`) and treats it as success because the model file has already been written. If you see this, your model is still in `models/wake_words/`.

---

## Why this is open

Wake-word training is usually behind a paywall (Picovoice charges per keyword) or trapped in a research notebook nobody can run. Clarity.V gives you the full pipeline because:

1. Your voice is yours. Training on it shouldn't require a third party.
2. Custom wake words are the difference between a toy and a daily driver.
3. Open training scripts mean forks can experiment, improve, and PR back.

The pipeline isn't perfect. If you find ways to make it work better — better augmentations, better TTS voice mixes, faster training — open an issue or PR. The README explains how.
