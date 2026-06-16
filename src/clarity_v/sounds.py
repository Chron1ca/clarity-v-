"""
Audio cue playback for activation / deactivation.

Knows where the bundled WAV cues live, and plays them via the platform
adapter (which uses winsound on Windows, Qt on other platforms). Safe
to disable globally via Settings — `play_*` are no-ops when disabled.

The cues are short chirps (~120 ms):
  - activate.wav    — rising pitch (recording started)
  - deactivate.wav  — falling pitch (recording ended)

The Person hears the direction of the chirp and knows which side of
the dictation cycle just fired, without looking at the screen.

Users can override the cue files via Settings (sound_activate_path /
sound_deactivate_path) to use their own sounds.
"""

from __future__ import annotations

from pathlib import Path

from clarity_v.platform._base import PlatformAdapter


# Default bundled cue paths, relative to the repo root.
def _bundled(name: str) -> Path:
    return Path(__file__).parent.parent.parent / "assets" / "sounds" / name


DEFAULT_ACTIVATE = _bundled("activate.wav")
DEFAULT_DEACTIVATE = _bundled("deactivate.wav")
DEFAULT_PASTE = _bundled("paste.wav")


class SoundCues:
    """Plays the cue tones if enabled.

    Three tones, direction- and texture-coded so the Person can tell
    what happened without looking at the screen:

      activate    — rising chirp; recording started
      deactivate  — falling chirp; recording ended, transcribing
      paste       — double pip at higher pitch; text landed at cursor,
                    the 5-second commit window for 'send' / 'enter'
                    starts now
    """

    def __init__(
        self,
        platform: PlatformAdapter,
        enabled: bool = True,
        activate_path: Path | None = None,
        deactivate_path: Path | None = None,
        paste_path: Path | None = None,
        volume: float = 0.5,
    ) -> None:
        self.platform = platform
        self.enabled = enabled
        self.activate_path = Path(activate_path) if activate_path else DEFAULT_ACTIVATE
        self.deactivate_path = (
            Path(deactivate_path) if deactivate_path else DEFAULT_DEACTIVATE
        )
        self.paste_path = Path(paste_path) if paste_path else DEFAULT_PASTE
        self.volume = volume

    def play_activate(self) -> None:
        """Play the activation cue (rising pitch). No-op if disabled."""
        if not self.enabled:
            return
        if not self.activate_path.exists():
            return
        self.platform.play_sound(str(self.activate_path), self.volume)

    def play_deactivate(self) -> None:
        """Play the deactivation cue (falling pitch). No-op if disabled."""
        if not self.enabled:
            return
        if not self.deactivate_path.exists():
            return
        self.platform.play_sound(str(self.deactivate_path), self.volume)

    def play_paste(self) -> None:
        """Play the paste cue (double pip).

        Fired the instant text lands at the cursor, marking the start
        of the post-paste commit window. The Person hears it whether
        or not they are looking at the screen — which is the whole
        point, because Whisper can take 10-60 seconds on long messages
        and the visual transition into COMMIT_WAITING is easy to miss.
        No-op if disabled.
        """
        if not self.enabled:
            return
        if not self.paste_path.exists():
            return
        self.platform.play_sound(str(self.paste_path), self.volume)
