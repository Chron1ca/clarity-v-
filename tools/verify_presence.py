"""
Phase 7 verification: glow bar + tray respond to state changes.

Driven entirely from the console window where this script is running.
The glow bar appears at the top of your screen; the tray icon goes to
the system tray. You stay in the CMD window the whole time.

  Enter  — advance to next state
  y      — pass: bar + tray render correctly
  n      — fail: something is wrong
  q      — abort

The bar cycles through five states (idle, recording, processing,
commit_waiting, error). No arbitrary timers — every transition
happens when you press Enter.

Usage:
    python tools/verify_presence.py
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from PySide6.QtCore import QObject, Signal  # noqa: E402

from clarity_v.presence import PresenceApp  # noqa: E402
from clarity_v.state import State, StateManager  # noqa: E402

STATES_IN_ORDER = [
    State.IDLE,
    State.RECORDING,
    State.PROCESSING,
    State.COMMIT_WAITING,
    State.ERROR,
]

# Human-readable description shown alongside each internal state name.
# The internal name is what's in the State enum; the description tells
# the Person what that state means in the dictation flow.
STATE_DESCRIPTIONS = {
    State.IDLE: "program on, ready (set alpha=0 to hide the bar at rest)",
    State.RECORDING: "recording your voice",
    State.PROCESSING: "transcribing with Whisper, pasting at cursor",
    State.COMMIT_WAITING: (
        "post-paste — 5s window for 'send' / 'enter' to fire Ctrl+Enter"
    ),
    State.ERROR: "abrupt stop — system error OR user cancel (Ctrl+Shift+Q)",
}


class InputBridge(QObject):
    """Cross-thread bridge: console-reader thread → Qt main thread.

    Qt signals are thread-safe; emitting from the reader thread schedules
    the slot on the Qt thread via a queued connection. That lets us read
    blocking ``input()`` in a daemon thread while Qt's event loop keeps
    the glow bar + tray icon responsive on the main thread.
    """

    advance = Signal()
    finish = Signal(bool)  # True = pass, False = fail
    abort = Signal()


def main() -> int:
    print("=" * 60)
    print("Clarity.V Phase 7 — Presence (glow bar + tray) verification")
    print("=" * 60)
    print()
    print("The glow bar should appear at the top of your screen.")
    print("The tray icon goes to your system tray (check the overflow")
    print("if you don't see it — Windows hides new tray icons by default).")
    print()
    print("Controls:")
    print("  Enter  — advance to next state")
    print("  y      — pass (bar + tray look correct)")
    print("  n      — fail (something is wrong)")
    print("  q      — abort")
    print()

    sm = StateManager()
    pres = PresenceApp(sm)

    bridge = InputBridge()
    holder = {"idx": 0, "result": None}

    def on_advance() -> None:
        holder["idx"] = (holder["idx"] + 1) % len(STATES_IN_ORDER)
        new_state = STATES_IN_ORDER[holder["idx"]]
        sm.set_state(new_state)
        desc = STATE_DESCRIPTIONS.get(new_state, "")
        print(
            f"  state {holder['idx'] + 1}/{len(STATES_IN_ORDER)}: "
            f"{new_state.value}  —  {desc}"
        )

    def on_finish(passed: bool) -> None:
        holder["result"] = passed
        pres.quit()

    def on_abort() -> None:
        holder["result"] = None
        pres.quit()

    bridge.advance.connect(on_advance)
    bridge.finish.connect(on_finish)
    bridge.abort.connect(on_abort)

    def reader() -> None:
        """Read console lines, fire Qt signals to drive the test."""
        while True:
            try:
                line = input().strip().lower()
            except EOFError:
                bridge.abort.emit()
                return
            if line == "":
                bridge.advance.emit()
            elif line == "y":
                bridge.finish.emit(True)
                return
            elif line == "n":
                bridge.finish.emit(False)
                return
            elif line == "q":
                bridge.abort.emit()
                return
            else:
                print(f"  (unknown input: {line!r}; use Enter / y / n / q)")

    threading.Thread(target=reader, daemon=True).start()

    # Set the initial state before the Qt loop starts so the bar
    # appears already showing IDLE color.
    first = STATES_IN_ORDER[0]
    sm.set_state(first)
    print(
        f"  state 1/{len(STATES_IN_ORDER)}: {first.value}  —  "
        f"{STATE_DESCRIPTIONS.get(first, '')}"
    )

    # pres.start() shows the bar + tray and blocks on Qt's exec().
    # Returns when pres.quit() is called from a signal slot.
    pres.start()

    print()
    if holder["result"] is True:
        print("PHASE 7 COMPLETE — Person confirmed bar + tray render correctly.")
        return 0
    if holder["result"] is False:
        print("PHASE 7 INCOMPLETE — Person reported issues. Fix and re-run.")
        return 1
    print("PHASE 7 ABORTED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
