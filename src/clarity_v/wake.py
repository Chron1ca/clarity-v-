"""
Wake-word detection via OpenWakeWord.

The wake detector runs continuously on every audio chunk fed to it.
It does NOT recognize arbitrary speech — only phrases that have a
trained ONNX model behind them. See ARCHITECTURE.md for the
wake-detector-vs-Whisper distinction.

For v1.0, Clarity.V ships with one of OpenWakeWord's pre-trained models
as the default wake word until a custom "clarity-v" model is trained.
Configurable via `WakeDetector(config)` so anyone can swap in their own
ONNX models (custom "clarity-v" model, "hey_jarvis", "alexa", whatever).

Public API:
    detector = WakeDetector(config)
    detector.feed(chunk)  # returns WakeEvent or None
    detector.reset()      # called after a detection so the model
                          # starts fresh for the next wake-word search
    detector.list_models()  # list of (name, threshold) pairs
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Default config — references the two trained models that ship with Clarity.V:
#
#   cv_go    — START wake. Threshold 0.5 (default-conservative — false-positives
#              cost the user a stray recording session).
#   cv_over  — STOP wake. Threshold 0.35 (lower — missed catches strand the
#              user in a recording they thought they ended, much worse than
#              a stray re-trigger that they can just say "go" to recover).
#
# If the ONNX files for these are missing on disk, wake.py falls back to
# OpenWakeWord's pre-trained `hey_jarvis` so first-run testing still works.
#
# Each entry in `models` may use either:
#   - a pre-trained model name resolved by OpenWakeWord (e.g., 'hey_jarvis',
#     'alexa', 'hey_mycroft') — no `model_path`
#   - a `model_path` pointing to a custom .onnx file you trained yourself
#     (see TRAINING.md). The detection key is the filename stem.
DEFAULT_CONFIG = {
    "models": [
        {
            "name": "cv_go",
            "model_path": "models/wake_words/cv_go.onnx",
            "threshold": 0.5,
            "role": "start",
        },
        {
            "name": "cv_over",
            "model_path": "models/wake_words/cv_over.onnx",
            "threshold": 0.35,
            "role": "stop",
        },
    ],
    "cooldown_seconds": 0.5,
}


@dataclass
class WakeEvent:
    """A wake-word detection event."""

    model: str  # which wake model fired
    score: float  # detection confidence
    chunk_idx: int  # how many chunks have been fed when fired
    # (used by the orchestrator for accurate trim)
    timestamp: float
    role: str = "start"  # "start", "stop", or "toggle" (back-compat)


class WakeDetector:
    """Continuous wake-word detection.

    Feed every audio chunk via `feed(chunk)`. Returns a WakeEvent the
    instant a model's score exceeds its threshold (subject to cooldown).
    Returns None otherwise.

    Multi-model support: pass several models in `config["models"]` and
    each is checked on every chunk. First match wins (per chunk).

    Cooldown: prevents the same wake phrase firing twice in quick
    succession. Default 0.5 s.
    """

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or dict(DEFAULT_CONFIG)
        self._model_thresholds: dict[str, float] = {}
        self._model_roles: dict[str, str] = {}
        self._last_detection_at: float = 0.0
        self._chunk_count: int = 0
        self._model = None  # lazy-initialized
        self._enabled = False
        self._load_model()

    # ─── Loading ──────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Lazy-load OpenWakeWord. Failure to load is non-fatal —
        the detector reports `enabled=False` and `feed()` returns None.

        This means the dictation engine can still run with hotkey-only
        input even if the wake model fails to load.
        """
        try:
            import openwakeword.utils as oww_utils
            from openwakeword.model import Model as WakeWordModel
        except ImportError as e:
            print(f"[WakeDetector] openwakeword not installed: {e}")
            return

        # OpenWakeWord ships without its preprocessing models
        # (melspectrogram.onnx, embedding_model.onnx) — those have to be
        # downloaded on first use. The engine self-heals: if either file
        # is missing on disk, run the bundled downloader once, silently.
        import openwakeword

        oww_models_dir = Path(openwakeword.__file__).parent / "resources" / "models"
        required = ("melspectrogram.onnx", "embedding_model.onnx")
        missing = [m for m in required if not (oww_models_dir / m).exists()]
        if missing:
            print(
                f"[WakeDetector] First-run setup: downloading OpenWakeWord "
                f"preprocessing models {missing}..."
            )
            try:
                oww_utils.download_models()
                print("[WakeDetector] Preprocessing models downloaded.")
            except Exception as e:
                print(f"[WakeDetector] Download failed: {type(e).__name__}: {e}")
                # Don't return — let the load attempt proceed and emit
                # the real "Load failed" error if the prereqs are still
                # absent.

        models_config = self.config.get("models", [])
        if not models_config:
            print("[WakeDetector] No wake models configured.")
            return

        # Each entry can be either a custom ONNX path (model_path) OR a
        # pre-trained openwakeword model name. Build the list passed to
        # openwakeword.Model plus per-model maps for threshold + role.
        wakeword_models: list[str] = []
        self._model_thresholds = {}
        self._model_roles = {}
        skipped: list[str] = []

        for entry in models_config:
            name = entry["name"]
            threshold = entry.get("threshold", 0.5)
            role = entry.get("role", "start")  # default: starts dictation
            model_path = entry.get("model_path")

            if model_path:
                p = Path(model_path)
                if not p.exists():
                    print(
                        f"[WakeDetector] Missing model file: {p} "
                        f"(entry {name!r} skipped — fallback expected)"
                    )
                    skipped.append(name)
                    continue
                # openwakeword resolves by path or name; pass absolute.
                wakeword_models.append(str(p.resolve()))
                # Detection output keys on the filename stem when loaded
                # from path. Use that as the lookup key.
                detection_key = p.stem
                self._model_thresholds[detection_key] = threshold
                self._model_roles[detection_key] = role
                print(f"[WakeDetector] Loading custom model: {p} (role={role})")
            else:
                wakeword_models.append(name)
                self._model_thresholds[name] = threshold
                self._model_roles[name] = role

        if not wakeword_models:
            print(
                "[WakeDetector] All configured models missing — fallback "
                "to OpenWakeWord pre-trained 'hey_jarvis' (role=start)."
            )
            wakeword_models = ["hey_jarvis"]
            self._model_thresholds["hey_jarvis"] = 0.5
            self._model_roles["hey_jarvis"] = "start"

        try:
            self._model = WakeWordModel(wakeword_models=wakeword_models)
            self._enabled = True
            for name, thr in self._model_thresholds.items():
                print(f"[WakeDetector] Loaded: {name!r} (threshold {thr})")
            if skipped:
                print(f"[WakeDetector] Skipped (missing files): {skipped}")
        except Exception as e:
            print(f"[WakeDetector] Load failed: {type(e).__name__}: {e}")
            self._enabled = False

    # ─── Public API ───────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        """True if the wake model loaded successfully."""
        return self._enabled

    def feed(self, chunk: np.ndarray) -> WakeEvent | None:
        """Feed one audio chunk. Returns WakeEvent if a wake fired, else None.

        Args:
            chunk: int16 ndarray, typically 4000 samples (250 ms at 16 kHz).

        Returns:
            WakeEvent or None. The chunk_idx field on the event is the
            count of chunks fed BEFORE this one — useful for the
            orchestrator to know where in its buffer the wake fired.
        """
        if not self._enabled:
            return None

        self._chunk_count += 1

        prediction = self._model.predict(chunk)
        cooldown = self.config.get("cooldown_seconds", 0.5)
        now = time.time()

        for name, threshold in self._model_thresholds.items():
            score = prediction.get(name, 0.0)
            if score > threshold:
                if now - self._last_detection_at < cooldown:
                    # Cooldown active — suppress this detection.
                    continue
                self._last_detection_at = now
                role = self._model_roles.get(name, "start")
                return WakeEvent(
                    model=name,
                    score=float(score),
                    chunk_idx=self._chunk_count - 1,
                    timestamp=now,
                    role=role,
                )
        return None

    def reset(self) -> None:
        """Reset the model's internal state after a detection.

        OpenWakeWord accumulates context across chunks for detection;
        after firing, we reset so the next wake word starts from a clean
        slate. Also clears the chunk counter so the next event's
        chunk_idx is relative to the next listening session.
        """
        if self._model is not None:
            with contextlib.suppress(Exception):
                self._model.reset()
        self._chunk_count = 0

    def list_models(self) -> list[tuple[str, float]]:
        """Return (model_name, threshold) pairs for all loaded models."""
        return [(n, t) for n, t in self._model_thresholds.items()]


# ─── Convenience ──────────────────────────────────────────────────────


def from_dict(d: dict) -> WakeDetector:
    """Build a WakeDetector from a parsed config dict (e.g., from JSON)."""
    return WakeDetector(d)
