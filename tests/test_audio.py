"""
Audio helpers — unit tests for the non-mic-dependent pieces.

The mic-dependent pieces (start/stop, on_chunk firing, real recording)
are verified interactively by tools/verify_audio.py since they require
hardware. These tests cover the helper functions (concat, rms_energy)
and the data classes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np

from clarity_v.audio import AudioDevice, concat, list_devices, rms_energy


class TestConcat:
    def test_empty(self):
        result = concat([])
        assert result.dtype == np.int16
        assert len(result) == 0

    def test_single_chunk(self):
        c = np.array([1, 2, 3, 4], dtype=np.int16)
        result = concat([c])
        assert len(result) == 4
        assert (result == c).all()

    def test_multiple_chunks(self):
        a = np.array([1, 2], dtype=np.int16)
        b = np.array([3, 4, 5], dtype=np.int16)
        result = concat([a, b])
        assert len(result) == 5
        assert list(result) == [1, 2, 3, 4, 5]


class TestRMSEnergy:
    def test_silence(self):
        silence = np.zeros(16000, dtype=np.int16)
        assert rms_energy(silence) == 0.0

    def test_empty(self):
        assert rms_energy(np.zeros(0, dtype=np.int16)) == 0.0

    def test_full_scale_sine(self):
        # 440 Hz sine at full scale → RMS = 1/sqrt(2) ≈ 0.707
        t = np.arange(16000) / 16000
        sine = (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
        energy = rms_energy(sine)
        assert 0.65 < energy < 0.75, f"Expected ~0.707, got {energy}"

    def test_low_level_audio_above_silence_threshold(self):
        # Audio at 1% amplitude — typical quiet-room mic noise floor.
        t = np.arange(16000) / 16000
        sine = (np.sin(2 * np.pi * 100 * t) * 32767 * 0.01).astype(np.int16)
        energy = rms_energy(sine)
        # Above absolute silence, below speech threshold.
        assert 0.0 < energy < 0.05


class TestAudioDevice:
    def test_dataclass_fields(self):
        d = AudioDevice(
            index=0,
            name="Test Mic",
            max_input_channels=2,
            default_samplerate=48000.0,
        )
        assert d.index == 0
        assert d.name == "Test Mic"
        assert d.max_input_channels == 2
        assert d.default_samplerate == 48000.0


class TestListDevices:
    def test_returns_list(self):
        # On any sensible CI/dev machine this should succeed.
        # Hardware-less environments may have no devices; that's fine —
        # the test just asserts the function executes and returns a list.
        result = list_devices()
        assert isinstance(result, list)
        for d in result:
            assert isinstance(d, AudioDevice)
            assert d.max_input_channels > 0
