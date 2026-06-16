"""
DictationEngine — the state machine that orchestrates the full flow.

Composes every other module into the voice-to-text loop:

    IDLE
      ↓  wake fires
    RECORDING
      ↓  cv_over wake fires OR stop keybind (silence opt-in only)
    PROCESSING
      ↓  whisper + filters + dictionary + paste
    COMMIT_WAITING
      ↓  (handed off to commit.py — post-paste window)
    IDLE

Stop signal — by default, ONLY explicit Person signals end a recording:
the `cv_over` stop wake or the stop keybind. The AI never autonomously
decides the Person is done. Silence-detection and wake-refire exist as
opt-in alternatives (silence_seconds_to_stop > 0).

Cleanup discipline: every short-circuit (empty audio / too short /
hallucination-stripped) returns to IDLE explicitly. The state machine
never leaks.

Threading: the sounddevice callback runs on the audio thread and
feeds chunks through `_on_chunk`. State transitions and Whisper work
happen on a worker thread to keep the audio callback non-blocking.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from clarity_v.audio import AudioCapture, concat, rms_energy
from clarity_v.buffer import LastDictationBuffer
from clarity_v.dictation_log import DictationLog
from clarity_v.dictionary import Dictionary
from clarity_v.platform import get_adapter
from clarity_v.platform._base import PlatformAdapter
from clarity_v.sounds import SoundCues
from clarity_v.state import State, StateManager
from clarity_v.wake import WakeDetector
from clarity_v.whisper_engine import WhisperEngine

# ─── Defaults ─────────────────────────────────────────────────────────

SAMPLE_RATE = 16000
SILENCE_RMS_THRESHOLD = 0.005  # below = silence
SILENCE_SECONDS_TO_STOP = 0.0  # 0 = disabled (Person decides when message ends).
# The AI never autonomously ends a recording on its own timer. Set this
# to a positive number in Settings if you specifically want silence to
# auto-stop your dictation; default is OFF — stop via cv_over wake or
# the stop keybind.
MIN_RECORDING_SECONDS = 0.0  # 0 = no discard (Person decides what counts).
# The AI never decides a recording is "too short to matter." If you want
# very brief utterances ignored, set min_recording_seconds > 0 in Settings.
WAKE_TRIM_CHUNKS = 6  # ~1.5 s at 4000 samples / 16 kHz
COMMIT_WINDOW_SECONDS = 0.0  # 0 = no auto commit window (Person decides).
# After paste, no automatic listening-for-action-words window opens. The
# engine returns straight to IDLE. Set commit_window_seconds > 0 in
# Settings if you specifically want a post-paste window to catch action
# words like "send" / "enter".


@dataclass
class DictationConfig:
    """Engine configuration. Override what you need."""

    dictionary_path: Path | None = None  # None = load_default
    whisper_model: str = "medium"
    whisper_device: str = "auto"
    language_lock: str = ""  # "" = auto-detect
    whisper_initial_prompt: str = ""  # "" = use WhisperEngine default
    wake_config: dict | None = None  # None = WakeDetector default
    audio_device: int | None = None  # None = system default
    silence_rms_threshold: float = SILENCE_RMS_THRESHOLD
    silence_seconds_to_stop: float = SILENCE_SECONDS_TO_STOP
    min_recording_seconds: float = MIN_RECORDING_SECONDS
    commit_window_seconds: float = COMMIT_WINDOW_SECONDS
    profiles_enabled: bool = True
    in_dictation_commands_enabled: bool = True
    wake_words_enabled: bool = True
    vocabulary_blacklist: str = ""

    # Computed in __post_init__
    _silence_chunks_to_stop: int = field(default=0, init=False)

    def __post_init__(self):
        # blocksize 4000 = 0.25 s, so 2.5 s of silence = 10 chunks
        chunks_per_sec = SAMPLE_RATE / 4000
        self._silence_chunks_to_stop = int(
            round(self.silence_seconds_to_stop * chunks_per_sec)
        )


class DictationEngine:
    """The full voice-to-text orchestrator."""

    def __init__(
        self,
        config: DictationConfig | None = None,
        state_manager: StateManager | None = None,
        platform: PlatformAdapter | None = None,
        last_dictation_buffer: LastDictationBuffer | None = None,
        dictation_log: DictationLog | None = None,
        sound_cues: SoundCues | None = None,
    ) -> None:
        self.config = config or DictationConfig()
        self.state = state_manager or StateManager()
        # Independent of OS clipboard: holds last successful dictation
        # for the paste-last-dictation keybind.
        self.last_buffer = last_dictation_buffer or LastDictationBuffer()
        # Persistent log of every successful dictation (rotates at
        # ~500 KB per file under ~/.clarity_v/dictation_logs/).
        self.dictation_log = dictation_log
        # Activation / deactivation cue tones.
        self.sound_cues = sound_cues

        # Dictionary — default ships in dictionaries/default.json.
        if self.config.dictionary_path is None:
            repo_root = Path(__file__).parent.parent.parent
            self.config.dictionary_path = repo_root / "dictionaries" / "Default.json"
        self.dictionary = Dictionary.load(self.config.dictionary_path)
        self.dictionary.start_watching()

        # Wake detector.
        self.wake = WakeDetector(self.config.wake_config)
        self._wake_phrases: list[str] = [m[0] for m in self.wake.list_models()]

        # Whisper.
        self.whisper = WhisperEngine(
            model_size=self.config.whisper_model,
            device=self.config.whisper_device,
        )

        # Platform adapter.
        self.platform = platform or get_adapter()

        # Audio capture.
        self.audio = AudioCapture(
            device=self.config.audio_device,
            on_chunk=self._on_chunk,
        )

        # Internal state
        self._silence_run = 0
        # RLock, not Lock: _handle_wake holds the lock while calling
        # _end_recording (which also acquires it). With a plain Lock that
        # nests on the same thread and deadlocks — the recording would
        # stay at State.RECORDING forever with no exception raised,
        # because Lock.acquire() blocks the worker thread silently.
        # RLock is reentrant: same thread can re-acquire safely.
        self._worker_lock = threading.RLock()
        self._running = False
        self._is_ptt_held = False
        self._last_toggle_time = 0.0

    # ─── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Open mic, wake-detector primed, ready to listen."""
        if self._running:
            return
        self._running = True
        self.audio.start()
        self.state.set_state(State.IDLE)
        print(f"[Dictation] Listening for wake words: {self._wake_phrases}")

    def stop(self) -> None:
        """Close mic and reset state."""
        if not self._running:
            return
        self._running = False
        self.audio.stop()
        self.dictionary.stop_watching()
        self.state.set_state(State.IDLE)

    # ─── Audio thread callback ────────────────────────────────────────

    def _on_chunk(self, chunk: np.ndarray) -> None:
        """Runs on the audio thread for every chunk. Must not block."""
        current = self.state.state

        # Wake detection runs unless we're already processing.
        # During RECORDING, wake re-fire is the alternative-stop signal.
        if current != State.PROCESSING and self.config.wake_words_enabled:
            evt = self.wake.feed(chunk)
            if evt is not None:
                # Dispatch wake handling onto a worker thread.
                threading.Thread(
                    target=self._handle_wake,
                    args=(evt,),
                    daemon=True,
                ).start()
                return

        # Silence detection during RECORDING — only fires if the Person
        # explicitly opted in by setting silence_seconds_to_stop > 0.
        # Default is OFF: the AI does not decide when the message ends.
        # If PTT is held, we completely bypass silence detection.
        if current == State.RECORDING and self.config._silence_chunks_to_stop > 0 and not self._is_ptt_held:
            energy = rms_energy(chunk)
            if energy < self.config.silence_rms_threshold:
                self._silence_run += 1
                if self._silence_run >= self.config._silence_chunks_to_stop:
                    self._silence_run = 0
                    threading.Thread(
                        target=self._end_recording,
                        args=("silence",),
                        daemon=True,
                    ).start()
            else:
                self._silence_run = 0

    # ─── State handlers ──────────────────────────────────────────────

    def _handle_wake(self, evt) -> None:
        """Wake event — start or stop recording based on the model's role.

        Two trained models ship as defaults: `cv_go` (role=start) and
        `cv_over` (role=stop). Older single-model configs (or pre-trained
        OpenWakeWord fallbacks) default to role=start and use the
        "same wake fires twice = stop" pattern (toggle behavior).
        """
        role = getattr(evt, "role", "start")
        with self._worker_lock:
            current = self.state.state
            if current in (State.IDLE, State.COMMIT_WAITING):
                # Start wakes during idle or commit window → begin recording.
                # Stop wakes during idle or commit window → ignore (nothing to stop).
                if role == "start":
                    self._begin_recording()
            elif current == State.RECORDING:
                # Stop wakes end the recording cleanly (no wake-phrase trim
                # — the stop word was spoken separately, not as the tail
                # of the message).
                if role == "stop":
                    self._end_recording("wake_stop")
                # Start wakes during recording = re-fire toggle (Shelly
                # pattern). Trim wake-phrase off the end of the buffer.
                elif role == "start":
                    self._end_recording("wake_refire", wake_chunk_idx=evt.chunk_idx)

    def _begin_recording(self) -> None:
        print("[Dictation] Wake fired — recording...")
        if self.sound_cues is not None:
            self.sound_cues.play_activate()
        self.state.set_state(State.RECORDING)
        self._silence_run = 0
        self.wake.reset()
        self.audio.begin_record()

    def _end_recording(
        self,
        reason: str,
        wake_chunk_idx: int | None = None,
    ) -> None:
        with self._worker_lock:
            if self.state.state != State.RECORDING:
                return  # Already transitioned (race between silence + wake).
            print(f"[Dictation] Recording ended via {reason}")
            if self.sound_cues is not None:
                self.sound_cues.play_deactivate()
            self.state.set_state(State.PROCESSING)
            self.wake.reset()
            chunks = self.audio.end_record()

            # If stopped by a wake word (either refire or explicit stop), trim the wake-phrase tail.
            if reason in ("wake_refire", "wake_stop") and len(chunks) > WAKE_TRIM_CHUNKS:
                chunks = chunks[:-WAKE_TRIM_CHUNKS]

        # Call without lock so transcription and commit window don't block
        # new dictation starts! Offload to a background thread so the 
        # UI (e.g., floating button) doesn't freeze while transcribing.
        threading.Thread(target=self._process_recording, args=(chunks,), daemon=True).start()

    def _process_recording(self, chunks: list[np.ndarray]) -> None:
        """Transcribe, dictionary, paste. Then COMMIT_WAITING."""
        if not chunks:
            print("[Dictation] No audio captured.")
            self._return_to_idle()
            return

        audio = concat(chunks)
        duration = len(audio) / SAMPLE_RATE
        # Only discard "too short" recordings if Person explicitly opted
        # in (min_recording_seconds > 0). Default: 0, so every recording
        # is processed regardless of length. AI doesn't decide what counts.
        if (
            self.config.min_recording_seconds > 0
            and duration < self.config.min_recording_seconds
        ):
            print(f"[Dictation] Too short ({duration:.1f}s); ignoring.")
            self._return_to_idle()
            return

        # Transcribe.
        print(f"[Dictation] Transcribing {duration:.1f}s...")
        extra_hallucinations = []
        if self.config.vocabulary_blacklist:
            for p in self.config.vocabulary_blacklist.split(","):
                p_clean = p.strip().lower()
                if p_clean:
                    extra_hallucinations.append(p_clean)

        transcribe_kwargs = {
            "audio": audio,
            "language": self.config.language_lock or None,
            "wake_phrases": self._wake_phrases,
            "extra_hallucinations": extra_hallucinations if extra_hallucinations else None,
        }
        if self.config.whisper_initial_prompt:
            transcribe_kwargs["initial_prompt"] = self.config.whisper_initial_prompt
        result = self.whisper.transcribe(**transcribe_kwargs)
        if not result.text:
            print("[Dictation] Filtered to empty (hallucination or silence).")
            self._return_to_idle()
            return

        # Dictionary (substitutions + macros) and Stateful voice commands
        if self.config.in_dictation_commands_enabled:
            from clarity_v.text_processor import process_text_transforms
            if self.config.profiles_enabled:
                text = process_text_transforms(
                    result.text,
                    self.dictionary.voice_commands,
                    apply_substitutions_fn=self.dictionary.apply_substitutions,
                    expand_macros_fn=self.dictionary.expand_macros,
                )
            else:
                text = process_text_transforms(
                    result.text,
                    self.dictionary.voice_commands,
                )
        else:
            if self.config.profiles_enabled:
                text = self.dictionary.apply_substitutions(result.text)
                text = self.dictionary.expand_macros(text)
            else:
                text = result.text

        print(f"[Dictation] [{result.language}] {text!r}")

        # Stash to the LastDictationBuffer FIRST, before paste. This way
        # the paste-last keybind works even if paste-at-cursor fails for
        # any reason (cursor in wrong app, focus race, etc.).
        self.last_buffer.set(text, language=result.language)

        # Append to the persistent dictation log (rotates at 500 KB/file).
        if self.dictation_log is not None:
            try:
                self.dictation_log.append(text, language=result.language)
            except Exception as e:
                print(f"[Dictation] Log write failed: {e}")

        # Paste at cursor (uses OS clipboard with save/restore — does
        # NOT permanently hijack the user's clipboard).
        try:
            self.platform.paste_text(text)
        except Exception as e:
            print(f"[Dictation] Paste failed: {e}")
            self.state.set_error(f"Paste failed: {e}")
            time.sleep(1.5)
            self._return_to_idle()
            return

        # Audio cue: text just landed at the cursor. This is the moment
        # the Person needs to hear — Whisper may have taken 10-60 seconds
        # on a long dictation, and the visual transition into
        # COMMIT_WAITING is easy to miss. The double-pip tone tells them
        # the message is in and the 5-second commit window is now open.
        # Brief pause so the cue isn't itself captured by the commit
        # window's audio recording.
        if self.sound_cues is not None:
            self.sound_cues.play_paste()
            time.sleep(0.2)

        # Transition to COMMIT_WAITING — but ONLY if Person opted in by
        # setting commit_window_seconds > 0. Default: 0 (no auto window).
        # The AI does not unilaterally keep listening after paste; if the
        # Person wants action-word recognition, they enable it in Settings.
        if self.config.commit_window_seconds > 0 and self.config.in_dictation_commands_enabled:
            self.state.set_state(
                State.COMMIT_WAITING,
                {"text": text, "language": result.language},
            )
            from clarity_v import commit  # avoid circular import at module load

            commit.run_commit_window(self)
        self._return_to_idle()

    # ─── Cancellation (keybind: Ctrl+Shift+Q by default) ─────────────

    def cancel_dictation(self) -> str:
        """Cancel the current dictation cycle.

        Discards any in-flight recording, skips transcribe + paste,
        flashes the bar red briefly via ``State.ERROR`` (tagged with
        ``cancelled=True`` in the info dict so cause is recoverable),
        and returns to IDLE.

        Behavior by state:
          IDLE              — no-op (nothing to cancel)
          RECORDING         — discard the audio buffer, no transcribe
          PROCESSING        — Whisper may complete (it's mid-flight) but
                              the paste path checks state and skips
          COMMIT_WAITING    — end the commit window early
          ERROR             — fall through, return to IDLE on schedule

        Returns "cancelled" if action was taken, "noop" otherwise.
        """
        current = self.state.state
        with self._worker_lock:
            if current == State.IDLE:
                return "noop"
            self.state.set_state(
                State.ERROR,
                {"message": "Dictation cancelled by user", "cancelled": True},
            )
            if current in (State.RECORDING, State.COMMIT_WAITING):
                # Drop the captured audio; do NOT transcribe.
                self.audio.end_record()
                self.wake.reset()
            # PROCESSING / COMMIT_WAITING / ERROR fall through.
            # The commit window thread polls state and bails when it
            # sees something other than COMMIT_WAITING.

        # Hold the red flash briefly so the cancel is visible, then
        # return to IDLE. Done on a worker thread so the caller (the
        # keybind handler) returns immediately.
        threading.Thread(
            target=self._cancel_finish,
            daemon=True,
        ).start()
        return "cancelled"

    def _cancel_finish(self) -> None:
        """Hold the red flash, then return to IDLE."""
        time.sleep(0.8)
        self._return_to_idle()

    # ─── Push-To-Talk ────────────────────────────────────────────────
    
    def ptt_press(self) -> None:
        """Called when PTT key is held down."""
        with self._worker_lock:
            current = self.state.state
            if current in (State.IDLE, State.COMMIT_WAITING):
                self._is_ptt_held = True
                self._begin_recording()
                
    def ptt_release(self) -> None:
        """Called when PTT key is released."""
        with self._worker_lock:
            self._is_ptt_held = False
            current = self.state.state
            if current == State.RECORDING:
                self._end_recording("ptt_release")

    # ─── External toggle (keybind / floating button / etc.) ──────────

    def toggle_recording(self) -> str:
        """External entry point — start recording if idle, end if recording.

        This is what the floating start/stop button, the toggle keybind,
        and any other 'press to start/stop' surface should call. Voice
        wake words use a different path (see `_handle_wake`).

        Returns one of:
          - "started"   — went from IDLE to RECORDING
          - "stopped"   — went from RECORDING to PROCESSING
          - "busy"      — engine is in a transient state (PROCESSING) and ignores the toggle
        """
        now = time.monotonic()
        if now - getattr(self, '_last_toggle_time', 0.0) < 0.4:
            return "busy"
        self._last_toggle_time = now
        
        current = self.state.state
        with self._worker_lock:
            if current in (State.IDLE, State.COMMIT_WAITING):
                self._begin_recording()
                return "started"
            if current == State.RECORDING:
                # No wake_chunk_idx — treat as a clean stop, no trim.
                self._end_recording("toggle")
                return "stopped"
        return "busy"

    # ─── Paste-last-dictation (for the keybind) ───────────────────────

    def paste_last_dictation(self) -> bool:
        """Paste the most recent dictation at the current cursor.

        Uses the platform's paste_text (clipboard save/restore) so the
        user's OS clipboard is preserved. Returns True if something was
        pasted, False if the buffer was empty.

        This is what the configurable paste-last keybind invokes.
        """
        text = self.last_buffer.get()
        if not text:
            print("[Dictation] paste-last: buffer empty.")
            return False
        try:
            self.platform.paste_text(text)
            print(f"[Dictation] paste-last: re-pasted {len(text)} chars.")
            return True
        except Exception as e:
            print(f"[Dictation] paste-last failed: {e}")
            return False

    def _return_to_idle(self) -> None:
        """Hard reset to IDLE — the bar's resting "program on" color.

        Called from every short-circuit path: empty audio, too-short
        recording, hallucination-stripped, error, end of commit window.
        IDLE is the program's "I am here, ready" state; the bar shows
        whatever color the Person configured for it (or no color, if
        they set alpha=0).
        """
        with self._worker_lock:
            if self.state.state not in (State.IDLE, State.RECORDING):
                self._silence_run = 0
                self.state.set_state(State.IDLE)
                print("[Dictation] Ready.")
