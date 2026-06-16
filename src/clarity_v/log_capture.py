"""
Live log capture — intercepts stdout into a ring buffer.

The engine uses ``print()`` throughout for status messages
([Dictation], [WakeDetector], [Bridge], etc.). This module captures
those lines into a thread-safe circular buffer so the Settings UI
can display a live engine console.

Usage:
    from clarity_v.log_capture import install, get_lines_since

    install()                     # redirect stdout once at startup
    lines = get_lines_since(0)    # get all lines
    lines = get_lines_since(42)   # get lines after index 42
"""

from __future__ import annotations

import sys
import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class LogLine:
    """One captured log line with metadata."""
    index: int
    timestamp: float
    text: str


class _LogBuffer:
    """Thread-safe circular buffer of log lines."""

    def __init__(self, maxlen: int = 2000) -> None:
        self._buf: deque[LogLine] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._counter = 0

    def append(self, text: str) -> None:
        with self._lock:
            self._buf.append(LogLine(
                index=self._counter,
                timestamp=time.time(),
                text=text,
            ))
            self._counter += 1

    def get_since(self, after_index: int) -> list[LogLine]:
        """Return all lines with index > after_index."""
        with self._lock:
            return [ln for ln in self._buf if ln.index > after_index]

    def get_all(self) -> list[LogLine]:
        with self._lock:
            return list(self._buf)

    @property
    def latest_index(self) -> int:
        with self._lock:
            if self._buf:
                return self._buf[-1].index
            return -1


class _TeeWriter:
    """Wraps the real stdout and tees every write to the log buffer."""

    def __init__(self, original, buffer: _LogBuffer) -> None:
        self._original = original
        self._buffer = buffer
        self._line_buf = ""

    def write(self, text: str) -> int:
        # Always write to the original stdout
        result = self._original.write(text)
        # Buffer line-by-line (print() calls write() then write('\n'))
        self._line_buf += text
        while "\n" in self._line_buf:
            line, self._line_buf = self._line_buf.split("\n", 1)
            line = line.rstrip("\r")
            if line:  # skip empty lines
                self._buffer.append(line)
        return result

    def flush(self) -> None:
        # Flush any remaining partial line
        if self._line_buf.strip():
            self._buffer.append(self._line_buf.rstrip())
            self._line_buf = ""
        self._original.flush()

    # Delegate everything else to the original stdout
    def __getattr__(self, name):
        return getattr(self._original, name)


# ─── Module-level singleton ──────────────────────────────────────────

_buffer = _LogBuffer()
_installed = False


def install() -> None:
    """Redirect sys.stdout through the tee. Safe to call multiple times."""
    global _installed
    if _installed:
        return
    sys.stdout = _TeeWriter(sys.stdout, _buffer)
    _installed = True


def get_lines_since(after_index: int = -1) -> list[dict]:
    """Return log lines with index > after_index as JSON-serializable dicts."""
    lines = _buffer.get_since(after_index)
    return [
        {"index": ln.index, "timestamp": ln.timestamp, "text": ln.text}
        for ln in lines
    ]


def get_latest_index() -> int:
    """Return the index of the most recent log line, or -1 if empty."""
    return _buffer.latest_index
