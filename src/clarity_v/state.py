"""
State machine and broadcaster.

Clarity.V's dictation flow is a small state machine. The presence layer
(glow bar, tray icon) renders state changes. The settings UI reads state.
The platform adapter may also react to state. The StateManager is the
single source of truth and the single broadcast point.

States (five):
    IDLE             — program on, ready; the bar's resting state
    RECORDING        — wake word fired, audio is being captured
    PROCESSING       — recording ended, Whisper is transcribing
    COMMIT_WAITING   — text pasted; listening 5 s for enter/send
    ERROR            — abrupt stop: system error OR user cancel
                       (distinguishable via info["cancelled"])

Transitions are not enforced — any state can move to any other (e.g., a
hard reset goes from any state to IDLE). The dictation orchestrator owns
which transitions are valid.

Thread safety: a single lock guards both the current state and the
subscriber list. Subscribers may be added/removed from any thread.
set_state() acquires the lock briefly to capture the subscriber list,
then releases before invoking callbacks (so a slow subscriber cannot
block another set_state call).
"""

from __future__ import annotations

import contextlib
import enum
import threading
from collections.abc import Callable
from typing import Any


class State(enum.Enum):
    """The current high-level state of the dictation engine.

    Five states. The bar is a presence indicator: it shows the program
    is on (IDLE) and changes color when something specific is happening
    (RECORDING / PROCESSING / COMMIT_WAITING / ERROR). User cancels
    surface as ERROR with ``info["cancelled"] = True`` — same red, same
    "abrupt stop" signal, distinguishable in code if needed.
    """

    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    COMMIT_WAITING = "commit_waiting"
    ERROR = "error"


# Callback signature: (new_state, info_dict)
Subscriber = Callable[[State, dict[str, Any]], None]


class StateManager:
    """Holds the current state, notifies subscribers on change."""

    def __init__(self, initial: State = State.IDLE) -> None:
        self._state: State = initial
        self._info: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._subscribers: list[Subscriber] = []

    # ─── Read ─────────────────────────────────────────────────────────

    @property
    def state(self) -> State:
        """Current state (atomic read)."""
        with self._lock:
            return self._state

    @property
    def info(self) -> dict[str, Any]:
        """Most recent info dict accompanying the current state."""
        with self._lock:
            return dict(self._info)

    # ─── Write ────────────────────────────────────────────────────────

    def set_state(
        self,
        new_state: State,
        info: dict[str, Any] | None = None,
    ) -> None:
        """Transition to `new_state` and notify all subscribers.

        Subscribers are invoked synchronously, in registration order, AFTER
        the lock is released. If a subscriber raises, the exception is
        caught and logged; other subscribers still run.
        """
        info_copy = dict(info) if info else {}
        with self._lock:
            self._state = new_state
            self._info = info_copy
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(new_state, info_copy)
            except Exception as e:
                print(f"[StateManager] Subscriber error: {e}")

    def set_error(self, message: str) -> None:
        """Convenience: transition to ERROR with a message."""
        self.set_state(State.ERROR, {"message": message})

    # ─── Subscribe ────────────────────────────────────────────────────

    def subscribe(self, callback: Subscriber) -> None:
        """Add a subscriber. Called on every subsequent state change."""
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        """Remove a previously-registered subscriber. No-op if missing."""
        with self._lock, contextlib.suppress(ValueError):
            self._subscribers.remove(callback)

    def clear_subscribers(self) -> None:
        """Drop all subscribers. Useful on shutdown."""
        with self._lock:
            self._subscribers.clear()


# ─── Module-level singleton (optional) ────────────────────────────────

_default_manager: StateManager | None = None


def get_default() -> StateManager:
    """Return the module-level StateManager singleton, creating it lazily.

    The engine can use its own StateManager directly; this singleton is for
    code that just wants 'the state manager' without threading dependencies
    through.
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = StateManager()
    return _default_manager
