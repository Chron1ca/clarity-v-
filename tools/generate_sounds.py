"""
Generate the default cue tones.

Run once to produce:
    assets/sounds/activate.wav     (upward chirp, "I'm listening")
    assets/sounds/deactivate.wav   (downward chirp, "I stopped")
    assets/sounds/paste.wav        (double pip, "text landed at cursor")

The tones are short (~100-150 ms), low-volume, and pleasant — designed
to be heard without being annoying. They are direction- and texture-
coded so a Person who is not watching the screen can tell what just
happened from the sound alone:

  rising chirp   = activation (recording started)
  falling chirp  = deactivation (recording ended; transcribing)
  double pip     = paste landed; commit window now open for 'send'/'enter'

The double pip sits at a distinctly higher pitch (1400 Hz) so it is
never confused with the activate/deactivate chirps (600-1000 Hz).

Regenerate with:
    python tools/generate_sounds.py

The WAVs are committed to the repo so users don't need to run this.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


SAMPLE_RATE = 44100  # CD-quality; widely supported
DURATION_S = 0.12  # 120 ms — long enough to register, short enough to ignore
VOLUME = 0.25  # 25% peak amplitude — quiet, not jarring


def _chirp(start_hz: float, end_hz: float, duration_s: float = DURATION_S):
    """Generate a sine-wave chirp from start_hz to end_hz."""
    n_samples = int(duration_s * SAMPLE_RATE)
    samples = []
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        # Linear frequency sweep
        freq = start_hz + (end_hz - start_hz) * (i / n_samples)
        # Sample value
        amp = math.sin(2 * math.pi * freq * t)
        # Fade in/out at edges (5% each side) to avoid clicks
        edge = int(n_samples * 0.05)
        if i < edge:
            amp *= i / edge
        elif i > n_samples - edge:
            amp *= (n_samples - i) / edge
        samples.append(int(amp * VOLUME * 32767))
    return samples


def _double_pip(
    freq_hz: float,
    pip_duration_s: float = 0.05,
    gap_s: float = 0.04,
):
    """Two short sine pips at the same pitch, separated by a brief silence.

    Total length = 2 * pip_duration_s + gap_s. With defaults that is
    ~140 ms. Used for the paste cue — sounds like "ding ding," clearly
    distinct from the single rising/falling chirps of activate/deactivate.
    """
    n_pip = int(pip_duration_s * SAMPLE_RATE)
    n_gap = int(gap_s * SAMPLE_RATE)
    samples = []
    edge = int(n_pip * 0.10)  # 10% fade-in/out per pip to avoid clicks
    for pip_idx in range(2):
        for i in range(n_pip):
            t = i / SAMPLE_RATE
            amp = math.sin(2 * math.pi * freq_hz * t)
            if i < edge:
                amp *= i / edge
            elif i > n_pip - edge:
                amp *= (n_pip - i) / edge
            samples.append(int(amp * VOLUME * 32767))
        if pip_idx == 0:
            samples.extend([0] * n_gap)
    return samples


def _save_wav(samples: list, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # int16
        w.setframerate(SAMPLE_RATE)
        data = b"".join(struct.pack("<h", s) for s in samples)
        w.writeframes(data)


def main() -> int:
    repo_root = Path(__file__).parent.parent
    sounds_dir = repo_root / "assets" / "sounds"

    # Activation: upward chirp 600 Hz -> 1000 Hz
    activate_samples = _chirp(start_hz=600, end_hz=1000)
    _save_wav(activate_samples, sounds_dir / "activate.wav")
    print(
        f"Wrote: {sounds_dir / 'activate.wav'} "
        f"(600 Hz -> 1000 Hz, {int(DURATION_S * 1000)} ms)"
    )

    # Deactivation: downward chirp 1000 Hz -> 600 Hz
    deactivate_samples = _chirp(start_hz=1000, end_hz=600)
    _save_wav(deactivate_samples, sounds_dir / "deactivate.wav")
    print(
        f"Wrote: {sounds_dir / 'deactivate.wav'} "
        f"(1000 Hz -> 600 Hz, {int(DURATION_S * 1000)} ms)"
    )

    # Paste: two short pips at 1400 Hz, clearly higher than the chirps
    # so the Person hears "text landed; commit window open" without
    # mistaking it for activate/deactivate.
    paste_samples = _double_pip(freq_hz=1400.0)
    _save_wav(paste_samples, sounds_dir / "paste.wav")
    print(f"Wrote: {sounds_dir / 'paste.wav'} (double pip @ 1400 Hz, ~140 ms)")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
