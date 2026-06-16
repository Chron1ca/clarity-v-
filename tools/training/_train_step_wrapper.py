"""
Training-step wrapper: Windows compatibility shims + VRAM cap.

OpenWakeWord's training pipeline has two issues on Windows that this
wrapper papers over:

  1. It imports `torchaudio.set_audio_backend`, which was removed in
     newer torchaudio versions. Without a patch, training fails to
     even import.

  2. It uses torchcodec for audio I/O, which doesn't work on Windows.
     We swap in soundfile (which IS on Windows) and back-end
     `torchaudio.load` / `torchaudio.info` with soundfile-powered
     equivalents.

The wrapper also caps GPU VRAM usage at 75% so you can still use your
machine for other things while training runs (training easily takes
1-2 hours on a CUDA GPU, 6-12 hours on CPU).

This file is `exec()`'d by `train.py` with the target training config
substituted in. It is not meant to be run directly.

Variables expected at exec time (substituted by train.py):
    WORK_DIR    — path to wake_training directory
    PIPER_PATH  — path to piper-sample-generator
    TRAIN_PY    — path to openwakeword's train.py
    CONFIG_PATH — path to the training config yaml
    STEP_FLAG   — one of '--generate_clips', '--augment_clips', '--train_model'
"""

import os
import runpy
import sys
from collections import namedtuple

import soundfile as sf
import torch
import torchaudio


def _noop_set_backend(_x):
    """No-op replacement for the removed torchaudio.set_audio_backend."""


if not hasattr(torchaudio, "set_audio_backend"):
    torchaudio.set_audio_backend = _noop_set_backend


# Soundfile-backed replacements for torchaudio.load / .info.
# Newer torchaudio defers to torchcodec which is unavailable on Windows.


def _soundfile_load(filepath, *_args, **_kwargs):
    data, sr = sf.read(str(filepath), dtype="float32")
    if data.ndim == 1:
        data = data.reshape(1, -1)
    else:
        data = data.T
    return torch.from_numpy(data), sr


_AudioInfo = namedtuple("AudioInfo", ["num_frames", "num_channels", "sample_rate"])


def _soundfile_info(filepath):
    info = sf.info(str(filepath))
    return _AudioInfo(
        num_frames=info.frames,
        num_channels=info.channels,
        sample_rate=info.samplerate,
    )


torchaudio.load = _soundfile_load
torchaudio.info = _soundfile_info


# Cap VRAM usage at 75% so the user can still browse / watch video
# during training (which is hours long).
if torch.cuda.is_available():
    torch.cuda.set_per_process_memory_fraction(0.75, 0)


# Inject training paths and run OpenWakeWord's train script with the
# given config + step flag. These globals are set by train.py before
# exec() picks this file up.
WORK_DIR = os.environ["CLARITY_TRAIN_WORK_DIR"]
PIPER_PATH = os.environ["CLARITY_TRAIN_PIPER_PATH"]
TRAIN_PY = os.environ["CLARITY_TRAIN_TRAIN_PY"]
CONFIG_PATH = os.environ["CLARITY_TRAIN_CONFIG_PATH"]
STEP_FLAG = os.environ["CLARITY_TRAIN_STEP_FLAG"]

os.chdir(WORK_DIR)
sys.path.insert(0, PIPER_PATH)
sys.argv = ["train.py", "--training_config", CONFIG_PATH, STEP_FLAG]
runpy.run_path(TRAIN_PY, run_name="__main__")
