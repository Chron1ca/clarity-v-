"""
Persistent dictation log with size-based rotation.

Every successful transcription is appended as one JSON line:

    {"ts": "2026-05-22T15:42:11Z", "lang": "en", "text": "..."}

Lines accumulate in the current log file. When the current file reaches
the rotation threshold (default 500 KB), a new file starts. Files are
numbered `dictation_log_001.jsonl`, `dictation_log_002.jsonl`, etc.

Why JSONL not plain text: it preserves structure (timestamp + language
+ text), is greppable, and survives newlines inside dictated text.

Why size-based rotation not time-based: people dictate at very different
rates; size-based gives consistent file sizes regardless of usage pace.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOG_DIR = Path.home() / ".clarity_v" / "dictation_logs"
DEFAULT_MAX_BYTES = 500 * 1024  # 500 KB
LOG_FILENAME_RE = re.compile(r"^dictation_log_(\d{3})\.jsonl$")


class DictationLog:
    """Append-only dictation log with size rotation.

    Thread-safe: a single lock guards `append()`. Read-side iteration
    via `iter_entries()` is also locked but is intended for inspection,
    not high-frequency reads.
    """

    def __init__(
        self,
        log_dir: Path | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.log_dir = log_dir or DEFAULT_LOG_DIR
        self.max_bytes = max_bytes
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._current_path: Path = self._discover_current_path()

    # ─── Path discovery + rotation ────────────────────────────────────

    def _discover_current_path(self) -> Path:
        """Find the highest-numbered log file, or start at 001."""
        existing = sorted(
            p
            for p in self.log_dir.glob("dictation_log_*.jsonl")
            if LOG_FILENAME_RE.match(p.name)
        )
        if not existing:
            return self.log_dir / "dictation_log_001.jsonl"
        return existing[-1]

    def _next_log_path(self) -> Path:
        """Compute the next file in the sequence."""
        m = LOG_FILENAME_RE.match(self._current_path.name)
        n = int(m.group(1)) if m else 0
        return self.log_dir / f"dictation_log_{n + 1:03d}.jsonl"

    def _rotate_if_needed(self) -> None:
        """If the current file exceeds max_bytes, move to the next file."""
        if not self._current_path.exists():
            return
        try:
            size = self._current_path.stat().st_size
        except OSError:
            return
        if size >= self.max_bytes:
            self._current_path = self._next_log_path()

    # ─── Public API ───────────────────────────────────────────────────

    def append(self, text: str, language: str = "") -> None:
        """Add one dictation to the log. Thread-safe."""
        if not text:
            return
        entry = {
            "ts": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "lang": language,
            "text": text,
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"

        with self._lock:
            self._rotate_if_needed()
            # Open in append+text mode; UTF-8 is the universal choice for
            # multi-language dictation (PT/EN/JA all work transparently).
            with open(self._current_path, "a", encoding="utf-8") as f:
                f.write(line)

    @property
    def current_path(self) -> Path:
        with self._lock:
            return self._current_path

    def list_files(self) -> list[Path]:
        """Return all log files in chronological order."""
        return sorted(
            p
            for p in self.log_dir.glob("dictation_log_*.jsonl")
            if LOG_FILENAME_RE.match(p.name)
        )

    def iter_entries(self) -> Iterator[dict]:
        """Iterate every entry across all log files, oldest first.

        Yields decoded JSON entries. Malformed lines are skipped silently
        (a log shouldn't crash readers on a partial write).
        """
        for path in self.list_files():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue


# ─── Module-level singleton (optional convenience) ────────────────────

_default_log: DictationLog | None = None


def get_default() -> DictationLog:
    """Return the module-level singleton, creating lazily."""
    global _default_log
    if _default_log is None:
        _default_log = DictationLog()
    return _default_log
