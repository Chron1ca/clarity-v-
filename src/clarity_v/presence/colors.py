"""
State → color mapping for the presence layer.

Each state in the engine maps to a glow bar color. Defaults are tuned
for the dark-background "ambient awareness" feel (subtle when idle,
bright when active, alarming when error). All colors are configurable
from the settings UI.
"""

from __future__ import annotations

from dataclasses import dataclass

from clarity_v.state import State


@dataclass
class GlowColors:
    """RGBA colors for each state, plus the idle intensity multiplier.

    Stored as (R, G, B, A) tuples with values 0-255. The presence
    overlay reads these on every state change.

    Default palette:
      - idle (program on, ready)         = soft blue (alpha=0 hides bar)
      - recording your dictation         = green
      - transcribing (Whisper running)   = orange
      - commit_waiting (post-paste 5 s)  = teal
      - error / user-cancelled            = red

    All five are individually configurable in settings.
    """

    # IDLE = program on, nothing actively happening. The bar's resting
    # color. Soft blue chosen as a subtle, ambient "I am here" signal.
    # Set alpha to 0 in Settings if you want the bar invisible at rest
    # and visible only when something is happening.
    idle: tuple[int, int, int, int] = (51, 153, 255, 120)
    recording: tuple[int, int, int, int] = (51, 204, 51, 240)  # green
    processing: tuple[int, int, int, int] = (255, 140, 0, 240)  # orange
    # Teal so the 5-second post-paste window reads as a distinct state.
    # The audio "paste" cue marks the moment it starts; the color is
    # secondary for users who can't see the bar.
    commit_waiting: tuple[int, int, int, int] = (100, 200, 220, 220)
    # ERROR also covers user-cancel — same red, same "abrupt stop"
    # signal. The info dict carries the cause if anyone cares.
    error: tuple[int, int, int, int] = (220, 30, 30, 240)

    def __post_init__(self):
        self._map: dict[State, tuple] = {
            State.IDLE: self.idle,
            State.RECORDING: self.recording,
            State.PROCESSING: self.processing,
            State.COMMIT_WAITING: self.commit_waiting,
            State.ERROR: self.error,
        }

    def for_state(self, state: State) -> tuple[int, int, int, int]:
        return self._map.get(state, self.idle)
