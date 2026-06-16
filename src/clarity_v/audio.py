"""
Audio capture.

Wraps sounddevice's InputStream with a chunk-buffer interface that the
wake detector and dictation engine both consume. The capture thread
owns the buffer; consumers receive each chunk via a callback or pull
the buffer en bloc when recording ends.

Design:
- The InputStream runs continuously once started — wake detection needs
  a constant audio feed, so we don't stop/start per recording.
- A simple flag (`is_recording`) gates whether incoming chunks are
  appended to the main buffer. Wake detection always sees every chunk.
- The buffer is a list of numpy arrays (one per chunk); `concat()`
  joins them into a single ndarray for transcription.
- `list_devices()` exposes input devices for the settings UI mic
  selector. Each device has an index, name, max input channels, and
  default sample rate.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import sounddevice as sd

# Whisper requires 16 kHz mono int16.
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_BLOCKSIZE = 4000  # 250 ms at 16 kHz


@dataclass
class AudioDevice:
    """A microphone input device."""

    index: int
    name: str
    max_input_channels: int
    default_samplerate: float


@dataclass
class AudioCapture:
    """Continuous microphone capture with chunk-by-chunk delivery.

    Lifecycle:
        cap = AudioCapture(on_chunk=lambda c: ...)
        cap.start()        # opens InputStream, callbacks begin firing
        cap.begin_record() # buffer starts accumulating chunks
        ...
        chunks = cap.end_record()  # returns list of chunks, clears buffer
        cap.stop()         # closes InputStream

    The on_chunk callback fires for EVERY chunk, regardless of whether
    recording is active. Wake detectors use this. Recording is just an
    additional layer that captures chunks into a buffer for later
    transcription.
    """

    sample_rate: int = DEFAULT_SAMPLE_RATE
    blocksize: int = DEFAULT_BLOCKSIZE
    device: int | None = None  # None = system default
    on_chunk: Callable[[np.ndarray], None] | None = None

    _stream: sd.InputStream | None = field(default=None, init=False)
    _buffer: list[np.ndarray] = field(default_factory=list, init=False)
    _is_recording: bool = field(default=False, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    # ─── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Open the InputStream. The on_chunk callback begins firing."""
        if self._stream is not None:
            return
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self.blocksize,
            device=self.device,
            callback=self._sd_callback,
        )
        self._stream.start()

    def stop(self) -> None:
        """Close the InputStream and discard any pending buffer."""
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
            with self._lock:
                self._is_recording = False
                self._buffer = []

    # ─── Recording control ───────────────────────────────────────────

    def begin_record(self) -> None:
        """Start appending incoming chunks to the buffer."""
        with self._lock:
            self._buffer = []
            self._is_recording = True

    def end_record(self) -> list[np.ndarray]:
        """Stop recording and return the captured chunks.

        The on_chunk callback continues firing for wake detection; only
        buffering stops.
        """
        with self._lock:
            self._is_recording = False
            chunks = self._buffer
            self._buffer = []
        return chunks

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._is_recording

    @property
    def buffer_seconds(self) -> float:
        """Current buffered duration in seconds (atomic snapshot)."""
        with self._lock:
            total_samples = sum(len(c) for c in self._buffer)
        return total_samples / self.sample_rate

    # ─── Internal ────────────────────────────────────────────────────

    def _sd_callback(self, indata, frames, time_info, status) -> None:
        """sounddevice callback — runs on the audio thread.

        Must not block. Copies the chunk into the buffer and forwards
        to the on_chunk consumer.
        """
        chunk = indata.copy().flatten()
        with self._lock:
            if self._is_recording:
                self._buffer.append(chunk)
        if self.on_chunk is not None:
            try:
                self.on_chunk(chunk)
            except Exception as e:
                print(f"[AudioCapture] on_chunk error: {e}")


# ─── Module-level helpers ─────────────────────────────────────────────


def list_devices() -> list[AudioDevice]:
    """Return all input-capable audio devices on this machine."""
    raw = sd.query_devices()
    devices: list[AudioDevice] = []
    for i, d in enumerate(raw):
        if d["max_input_channels"] <= 0:
            continue
        devices.append(
            AudioDevice(
                index=i,
                name=d["name"],
                max_input_channels=d["max_input_channels"],
                default_samplerate=d["default_samplerate"],
            )
        )
    return devices


def get_default_input() -> AudioDevice | None:
    """Return the system's default input device, or None if none exists."""
    try:
        default_idx = sd.default.device[0]
    except Exception:
        return None
    if default_idx is None or default_idx < 0:
        return None
    raw = sd.query_devices(default_idx)
    if raw["max_input_channels"] <= 0:
        return None
    return AudioDevice(
        index=default_idx,
        name=raw["name"],
        max_input_channels=raw["max_input_channels"],
        default_samplerate=raw["default_samplerate"],
    )


def concat(chunks: list[np.ndarray]) -> np.ndarray:
    """Join a list of chunks into one ndarray. Empty list → 0-length."""
    if not chunks:
        return np.zeros(0, dtype=np.int16)
    return np.concatenate(chunks)


def rms_energy(chunk: np.ndarray) -> float:
    """Compute RMS energy of an int16 audio chunk in [0.0, 1.0].

    Used by silence detection: when N consecutive chunks all have RMS
    below a threshold (~0.005-0.01), the recording is considered ended.
    """
    if len(chunk) == 0:
        return 0.0
    # Normalize int16 to float [-1, 1], compute RMS.
    f = chunk.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(f * f)))
