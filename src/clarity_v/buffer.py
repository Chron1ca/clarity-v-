"""
LastDictationBuffer — a separate "clipboard" for Clarity.V's last dictation.

The point: the user's OS clipboard is sacred. If they Ctrl+C'd something
before dictating, then dictated, then Ctrl+V — they should get back what
they Ctrl+C'd, NOT the dictation.

This buffer is independent. It holds the most recent successful
dictation. A dedicated keybind (configurable; e.g., Ctrl+Shift+V)
pastes from THIS buffer, not the OS clipboard. The user's normal
copy/paste keeps working untouched.

The buffer is in-memory only. It does not persist across app restarts.
(That's intentional — last-dictation is a session-scoped convenience,
not a long-term store. The dictation log handles persistence.)

Public surface:
    from clarity_v.buffer import LastDictationBuffer

    buf = LastDictationBuffer()
    buf.set("hello world", language="en")
    text = buf.get()        # "hello world"
    info = buf.get_info()   # {"text": ..., "language": ..., "timestamp": ...}
    buf.clear()
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class DictationEntry:
    text: str
    language: str = ""
    timestamp: float = field(default_factory=time.time)


class LastDictationBuffer:
    """Thread-safe holder for the most recent dictation.

    There is exactly one current entry. Setting a new entry replaces
    the previous. `get()` returns the text (or empty string if nothing
    has been dictated yet).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entry: DictationEntry | None = None

    def set(self, text: str, language: str = "") -> None:
        """Replace the buffer contents with new dictation text."""
        with self._lock:
            self._entry = DictationEntry(text=text, language=language)

    def get(self) -> str:
        """Return the buffered text, or empty string if nothing buffered."""
        with self._lock:
            if self._entry is None:
                return ""
            return self._entry.text

    def get_info(self) -> DictationEntry | None:
        """Return the full entry (text + language + timestamp), or None."""
        with self._lock:
            if self._entry is None:
                return None
            return DictationEntry(
                text=self._entry.text,
                language=self._entry.language,
                timestamp=self._entry.timestamp,
            )

    def clear(self) -> None:
        """Drop the current entry."""
        with self._lock:
            self._entry = None

    def is_empty(self) -> bool:
        with self._lock:
            return self._entry is None


# ─── Module-level singleton (optional convenience) ────────────────────

_default_buffer: LastDictationBuffer | None = None


def get_default() -> LastDictationBuffer:
    """Return the module-level singleton, creating lazily."""
    global _default_buffer
    if _default_buffer is None:
        _default_buffer = LastDictationBuffer()
    return _default_buffer
