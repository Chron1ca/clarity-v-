"""
Dictionary — substitutions, macros, and voice commands.

A Clarity.V dictionary is a JSON file with three categories:

  * substitutions  — phrase → phrase replacement (fix Whisper mishears,
                     inject jargon, swap acronyms)
  * macros         — phrase → multi-line template (the coding dictionary;
                     say a short trigger, get a full code snippet)
  * voice_commands — phrase → action spec (stop/enter/send/new paragraph
                     and friends), tagged with `phase` for when they fire
                     ("during" dictation, "after" the paste)

Dictionaries can inherit from each other via the `extends` field, so
`python.json` inherits all of `default.json`'s substitutions and only adds
the Python-specific ones. Child entries override parent entries by key.

Hot reload: call `dictionary.start_watching()` to spawn a daemon thread
that re-loads the file (and its parents) when any of them is modified.
Listeners registered with `on_reload(callback)` fire after a successful
reload. Failed reloads (JSON parse error, missing parent) keep the
previous in-memory state and log the error — never crash.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _strip_comments(d: dict[str, Any]) -> dict[str, Any]:
    """Drop `_comment` keys from a dict (human notes in JSON)."""
    return {k: v for k, v in d.items() if k != "_comment"}


class Dictionary:
    """Loaded dictionary state: substitutions, macros, voice commands."""

    def __init__(
        self,
        name: str,
        description: str,
        substitutions: dict[str, str],
        macros: dict[str, str],
        voice_commands: dict[str, dict[str, Any]],
        source_paths: list[Path] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        # Stored lowercased for case-insensitive matching.
        self.substitutions = {k.lower(): v for k, v in substitutions.items()}
        self.macros = {k.lower(): v for k, v in macros.items()}
        self.voice_commands = {k.lower(): v for k, v in voice_commands.items()}
        # Source file paths (own + every parent), used by the file watcher.
        self.source_paths: list[Path] = source_paths or []

        # Hot-reload state. Baseline mtimes captured AT LOAD TIME so that
        # edits made between load() and start_watching() are still detected
        # by the watcher's first poll.
        self._reload_callbacks: list[Callable[[Dictionary], None]] = []
        self._watcher_thread: threading.Thread | None = None
        self._watcher_stop = threading.Event()
        self._last_mtimes: dict[Path, float] = {
            p: p.stat().st_mtime for p in self.source_paths if p.exists()
        }

    # ─── Loading ──────────────────────────────────────────────────────

    @classmethod
    def load(
        cls,
        path: str | Path,
        _stack: list[Path] | None = None,
    ) -> Dictionary:
        """Load a dictionary, resolving `extends:` chain.

        Args:
            path: file path to the dictionary JSON.
            _stack: internal, used for circular-extends detection.

        Raises:
            FileNotFoundError: if `path` or any extended parent is missing.
            ValueError: if the chain is circular.
            json.JSONDecodeError: if the JSON is malformed.
        """
        p = Path(path).resolve()
        if _stack is None:
            _stack = []
        if p in _stack:
            chain = " -> ".join(str(x.name) for x in _stack + [p])
            raise ValueError(f"Circular dictionary extends chain: {chain}")
        _stack = _stack + [p]

        data = json.loads(p.read_text(encoding="utf-8"))

        # Start from parent (if extends), then layer this file on top.
        if data.get("extends"):
            parent_name = data["extends"]
            # Resolve relative to this dictionary's directory.
            parent_path = (p.parent / f"{parent_name}.json").resolve()
            if not parent_path.exists():
                raise FileNotFoundError(
                    f"{p.name} extends '{parent_name}' but {parent_path} does not exist"
                )
            parent = cls.load(parent_path, _stack=_stack)
            subs = dict(parent.substitutions)
            macros = dict(parent.macros)
            vcs = dict(parent.voice_commands)
            sources = list(parent.source_paths)
        else:
            subs, macros, vcs = {}, {}, {}
            sources = []

        # Apply this file on top of inherited state.
        subs.update(_strip_comments(data.get("substitutions", {})))
        macros.update(_strip_comments(data.get("macros", {})))
        vcs.update(_strip_comments(data.get("voice_commands", {})))
        sources.append(p)

        return cls(
            name=data.get("name", p.stem),
            description=data.get("description", ""),
            substitutions=subs,
            macros=macros,
            voice_commands=vcs,
            source_paths=sources,
        )

    # ─── Text transformations ─────────────────────────────────────────

    def apply_substitutions(self, text: str) -> str:
        """Replace each substitution phrase in `text` with its value.

        Case-insensitive, word-boundary aware. Longer phrases match first
        so "u plane" wins over "u". Single-pass alternation regex — a
        replacement is never re-scanned, so subbing "u plane" → "U.Plane"
        does not then sub the "U" in the replacement.
        """
        return self._apply_table(text, self.substitutions)

    def expand_macros(self, text: str) -> str:
        """Expand macro triggers in `text` to their multi-line templates.

        Same matching rules as `apply_substitutions` — case-insensitive,
        word-boundary aware, longer triggers win, single-pass. Macro
        templates may contain real newlines (`\\n` in the JSON source).
        """
        return self._apply_table(text, self.macros)

    @staticmethod
    def _is_symbol_value(value: str) -> bool:
        """True if a substitution value is a symbol/punctuation character.

        Symbol substitutions get special treatment: surrounding commas and
        whitespace that Whisper inserts around pauses are consumed along
        with the trigger phrase. Without this, saying "Hello open quote
        world" produces ``Hello, ", world`` instead of ``Hello "world``.
        """
        v = value.strip()
        if not v:
            return False
        # Single non-alphanumeric character (e.g. "(", "\"", "*")
        if len(v) == 1 and not v.isalnum():
            return True
        # Short operator-like strings
        if v in ("==", "===", "!=", "->", "=>", "→", "- ", "\\"):
            return True
        # Newline/tab formatting
        if v in ("\n", "\n\n", "\t"):
            return True
        return False

    @staticmethod
    def _apply_table(text: str, table: dict[str, str]) -> str:
        """Apply a phrase→value table to text in one regex pass.

        For symbol/punctuation substitutions, also consumes surrounding
        commas and whitespace that Whisper inserts around spoken pauses.
        """
        if not text or not table:
            return text

        # Partition keys into symbol vs. non-symbol substitutions.
        symbol_keys = [k for k in table if Dictionary._is_symbol_value(table[k])]
        word_keys = [k for k in table if not Dictionary._is_symbol_value(table[k])]

        # Longest keys first so they win over shorter prefixes.
        all_keys = sorted(symbol_keys + word_keys, key=len, reverse=True)

        symbol_set = frozenset(k.lower() for k in symbol_keys)

        # Build a single alternation pattern. Each key is word-boundary
        # anchored; symbol keys additionally match optional surrounding
        # commas + space that Whisper inserts around pauses.
        parts = []
        for k in all_keys:
            escaped = re.escape(k)
            if k.lower() in symbol_set:
                # Consume optional leading/trailing comma or period + space.
                # Named groups would collide in alternation, so we use
                # a simple pattern: optional comma/period with optional space
                # on each side of the trigger word.
                parts.append(r"[,.]? ?\b" + escaped + r"\b[,.]? ?")
            else:
                parts.append(r"\b" + escaped + r"\b")

        pattern = "(?:" + "|".join(parts) + ")"

        def _replace(m: re.Match) -> str:
            # Strip surrounding punctuation/whitespace to find the key
            raw = m.group(0)
            key = raw.strip().strip(",.").strip().lower()
            value = table.get(key, raw)
            # For symbol substitutions that consumed commas, preserve
            # spacing so words don't merge with the symbol.
            if key in symbol_set:
                prefix = " " if m.start() > 0 else ""
                suffix = " " if m.end() < len(text) else ""
                return prefix + value + suffix
            return value

        result = re.sub(pattern, _replace, text, flags=re.IGNORECASE)
        # Clean up any double/triple spaces left after replacement
        result = re.sub(r" {2,}", " ", result).strip()
        return result

    def match_voice_command(
        self,
        text: str,
        phase: str,
    ) -> dict[str, Any] | None:
        """Return the voice command matching `text` if one fires for `phase`.

        Matching strategy: normalize text (lower, strip punctuation), then
        check each command's trigger phrase as a contained sub-word. Only
        commands tagged with the requested `phase` ("during" or "after")
        are considered.

        Returns the full command dict (with action, phase, and any extras),
        or None if no match.
        """
        if not text:
            return None
        normalized = re.sub(r"[.,!?]+", "", text.lower()).strip()
        if not normalized:
            return None
        # Longer triggers win to avoid "send" shadowing "send and clear".
        for trigger in sorted(self.voice_commands, key=len, reverse=True):
            cmd = self.voice_commands[trigger]
            if cmd.get("phase") != phase:
                continue
            pattern = r"\b" + re.escape(trigger) + r"\b"
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                return dict(cmd)
        return None

    # ─── Hot reload ───────────────────────────────────────────────────

    def on_reload(self, callback: Callable[[Dictionary], None]) -> None:
        """Register a callback invoked after every successful hot-reload."""
        self._reload_callbacks.append(callback)

    def start_watching(self, poll_interval_seconds: float = 1.0) -> None:
        """Spawn a daemon thread that re-loads on any source-file change.

        Call once after construction. Safe to call from any thread. Does
        nothing if already watching.
        """
        if self._watcher_thread and self._watcher_thread.is_alive():
            return
        self._watcher_stop.clear()
        self._watcher_thread = threading.Thread(
            target=self._watch_loop,
            args=(poll_interval_seconds,),
            daemon=True,
            name=f"Dictionary[{self.name}].watcher",
        )
        self._watcher_thread.start()

    def stop_watching(self) -> None:
        """Stop the watcher thread (if running)."""
        self._watcher_stop.set()
        if self._watcher_thread:
            self._watcher_thread.join(timeout=2.0)
            self._watcher_thread = None

    def _watch_loop(self, interval: float) -> None:
        # Use the baseline mtimes captured at load time (see __init__).
        while not self._watcher_stop.wait(interval):
            changed = False
            for p in self.source_paths:
                try:
                    mtime = p.stat().st_mtime
                except FileNotFoundError:
                    continue
                if self._last_mtimes.get(p) != mtime:
                    self._last_mtimes[p] = mtime
                    changed = True
            if changed:
                self._try_reload()

    def _try_reload(self) -> None:
        """Reload from disk. On failure, keep prior state intact."""
        # The "primary" path is the last entry in source_paths (child).
        try:
            primary = self.source_paths[-1]
            fresh = Dictionary.load(primary)
        except Exception as e:
            # Log and continue; never let a bad edit kill the engine.
            print(f"[Dictionary] Reload failed for {self.name}: {e}")
            return
        # Atomically swap in new state.
        self.name = fresh.name
        self.description = fresh.description
        self.substitutions = fresh.substitutions
        self.macros = fresh.macros
        self.voice_commands = fresh.voice_commands
        self.source_paths = fresh.source_paths
        for cb in list(self._reload_callbacks):
            try:
                cb(self)
            except Exception as e:
                print(f"[Dictionary] Reload callback error: {e}")


# ─── Convenience ──────────────────────────────────────────────────────


def load_default(dictionaries_dir: str | Path) -> Dictionary:
    """Convenience: load `dictionaries/Default.json` from a directory."""
    return Dictionary.load(Path(dictionaries_dir) / "Default.json")
