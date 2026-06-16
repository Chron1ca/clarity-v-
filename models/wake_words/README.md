# Wake-word models

This directory holds the ONNX wake-word models Clarity.V uses for detection.

## What goes here

`.onnx` files — small neural-net classifiers trained to fire when a specific phrase is said.

Clarity.V ships with two trained wake words by default in this directory:

- `cv_go.onnx` — role `start`, phrase `"see vee go"`, default threshold `0.5`. Begins dictation.
- `cv_over.onnx` — role `stop`, phrase `"see vee over"`, default threshold `0.35`. Ends dictation when the Person says so. (Silence-auto-stop is opt-in via Settings; default off.)

Both models are calibrated against the author's voice in the shipped [wake_config.json](../../wake_config.json); downstream users keep the conservative defaults until they recalibrate via `tools/training/calibrate.py`.

If both files are missing on disk for some reason, `wake.py` falls back to OpenWakeWord's bundled pre-trained `hey_jarvis` so the engine still runs and you can test the audio path.

## Adding your own model

The whole point is that this is your folder. Drop any compatible ONNX file here, point `wake_config.json` at it, restart Clarity.V.

To train one — including adapting it to your specific voice — see [TRAINING.md](../../TRAINING.md) at the repo root. The full pipeline is open-source and bundled in `tools/training/`. Your AI agent can walk you through it; the guide is written for AI-assisted use.

## Community models

A separate community-models repo is planned at `github.com/Chron1ca/clarity-v-community-wake-words`. If you train a model you're happy with, consider sharing it there so other people who want the same wake phrase can skip the training step.

When sharing, please include:

- The exact phrase
- Number of positive samples (synthetic + personal recordings)
- Validation accuracy from `tools/training/validate.py`
- Mix of TTS voices/languages used (affects which speakers it works for)

## Format

Clarity.V's `wake.py` accepts ONNX files produced by OpenWakeWord's training pipeline. Files from other wake-word systems (Porcupine, Snowboy, Picovoice) are NOT directly compatible — they use different model architectures and runtime APIs. Adapter files in `src/clarity_v/wake.py` could be PR'd for cross-system support; see the forkability note in [CONTRIBUTING.md](../../CONTRIBUTING.md).

## File naming

Use lowercase + underscores: `cv_go.onnx`, `okay_computer.onnx`, `bedtime_over.onnx`. The filename stem is what Clarity.V uses as the model's identifier in detection output and logs.

Names matter for `role` inference too. When `tools/training/validate.py` deploys a model, names containing `over`, `stop`, or `end` are inferred as `role=stop`; everything else is `role=start`. Pick a name that signals the role and the inference does the right thing — or set `role` explicitly in `wake_config.json`.
