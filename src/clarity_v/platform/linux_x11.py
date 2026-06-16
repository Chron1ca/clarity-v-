"""
Linux/X11 adapter — v1.1 support.

Strategy:
- Hotkeys via `pynput.keyboard.GlobalHotKeys` for press-only and `pynput.keyboard.Listener`
  for push-to-talk (tracking physical key states via a thread-safe pressed keys set).
- Synthetic input via `pynput.keyboard.Controller`.
- Paste via clipboard (`pyperclip`) + Ctrl+V — matches Windows implementation.
- Audio cues via PySide6 `QSoundEffect`.
- Topmost overlay: no-op since Qt's WindowStaysOnTopHint is natively honored by X11.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable

import pyperclip
from pynput import keyboard as pkb

from clarity_v.platform._base import PlatformAdapter


class LinuxX11Adapter(PlatformAdapter):
    """PlatformAdapter for Linux X11 sessions."""

    def __init__(self) -> None:
        self._hotkeys: dict[str, pkb.GlobalHotKeys] = {}
        self._listeners: list[pkb.Listener] = []
        self._controller = pkb.Controller()
        
        # Thread-safe tracking of currently pressed keys (for PTT/release combos)
        self._pressed_lock = threading.Lock()
        self._currently_pressed: set[str] = set()

    @property
    def name(self) -> str:
        return "Linux/X11"

    # ─── Hotkeys ────────────────────────────────────────────────────────

    def register_hotkey(
        self,
        combo: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None] | None = None,
        suppress: bool = True,
    ) -> None:
        # Press-only combos use pynput's GlobalHotKeys
        if on_release is None:
            pynput_combo = self._to_pynput_combo(combo)
            try:
                hotkey = pkb.GlobalHotKeys({pynput_combo: on_press})
                hotkey.start()
                self._hotkeys[combo] = hotkey
                print(f"[LinuxX11Adapter] Registered hotkey '{combo}' (pynput: '{pynput_combo}')")
            except Exception as e:
                print(f"[LinuxX11Adapter] Failed to register hotkey '{combo}': {e}")
            return

        # PTT combos require both press and release tracking
        keys_needed = self._parse_combo_keys(combo)
        combo_active = [False]
        release_timer = [None]

        def _fire_release():
            combo_active[0] = False
            on_release()

        def _on_press(key):
            normalized = self._normalize_key(key)
            if normalized:
                with self._pressed_lock:
                    self._currently_pressed.add(normalized)
                    
            if normalized in keys_needed:
                # Check if all required keys are currently pressed
                with self._pressed_lock:
                    all_pressed = all(k in self._currently_pressed for k in keys_needed)
                
                if all_pressed:
                    if release_timer[0] is not None:
                        release_timer[0].cancel()
                        release_timer[0] = None
                    if not combo_active[0]:
                        combo_active[0] = True
                        on_press()

        def _on_release(key):
            normalized = self._normalize_key(key)
            if normalized:
                with self._pressed_lock:
                    self._currently_pressed.discard(normalized)
                    
            if normalized in keys_needed:
                with self._pressed_lock:
                    all_pressed = all(k in self._currently_pressed for k in keys_needed)
                
                if combo_active[0] and not all_pressed:
                    if release_timer[0] is not None:
                        release_timer[0].cancel()
                    # 100ms debounce to filter out hardware/OS auto-repeat release blips
                    release_timer[0] = threading.Timer(0.1, _fire_release)
                    release_timer[0].start()

        listener = pkb.Listener(on_press=_on_press, on_release=_on_release)
        listener.start()
        self._listeners.append(listener)
        print(f"[LinuxX11Adapter] Registered release-aware hotkey '{combo}'")

    def unregister_all_hotkeys(self) -> None:
        for gh in self._hotkeys.values():
            try:
                gh.stop()
            except Exception:
                pass
        for listener in self._listeners:
            try:
                listener.stop()
            except Exception:
                pass
        self._hotkeys.clear()
        self._listeners.clear()
        with self._pressed_lock:
            self._currently_pressed.clear()
        print("[LinuxX11Adapter] Unregistered all hotkeys")

    # ─── Synthetic key events ──────────────────────────────────────────

    def send_key_combo(self, combo: str) -> None:
        keys = self._parse_combo_keys(combo)
        # Press modifiers first, then the primary key, then release in reverse order.
        modifier_order = ["ctrl", "shift", "alt", "win", "cmd"]
        held = sorted(
            keys, key=lambda k: modifier_order.index(k) if k in modifier_order else 99
        )
        try:
            for k in held:
                self._controller.press(self._key_for(k))
            time.sleep(0.02)  # short delay for the window manager to process modifier states
            for k in reversed(held):
                self._controller.release(self._key_for(k))
        except Exception:
            # Best-effort release to avoid leaving stuck keys on user's system
            for k in held:
                with contextlib.suppress(Exception):
                    self._controller.release(self._key_for(k))
            raise

    # ─── Paste at cursor ───────────────────────────────────────────────

    def paste_text(self, text: str) -> None:
        """Paste text at cursor using pyperclip clipboard + Ctrl+V flow."""
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = ""

        try:
            pyperclip.copy(text)
        except Exception as e:
            print(f"[LinuxX11Adapter] Clipboard copy failed: {e}")
            return

        # Wait up to 300ms for clipboard synchronization
        deadline = time.monotonic() + 0.3
        synced = False
        while time.monotonic() < deadline:
            try:
                if pyperclip.paste() == text:
                    synced = True
                    break
            except Exception:
                pass
            time.sleep(0.01)

        if not synced:
            print("[LinuxX11Adapter] Clipboard synchronization timeout. Aborting paste.")
            with contextlib.suppress(Exception):
                pyperclip.copy(previous)
            return

        # Send paste keyboard event
        self.send_key_combo("ctrl+v")

        # Asynchronously restore previous clipboard contents
        def _restore():
            time.sleep(0.4)
            with contextlib.suppress(Exception):
                pyperclip.copy(previous)

        threading.Thread(target=_restore, daemon=True).start()

    # ─── Audio cues ────────────────────────────────────────────────────

    def play_sound(self, wav_path: str, volume: float = 1.0) -> None:
        """Play WAV file using PySide6.QtMultimedia.QSoundEffect."""
        try:
            from PySide6.QtMultimedia import QSoundEffect
            from PySide6.QtCore import QUrl
            
            if not hasattr(self, "_sound_effects"):
                self._sound_effects = []
            
            # Flush finished sound effects
            self._sound_effects = [se for se in self._sound_effects if not se.isPlaying()]
            
            se = QSoundEffect()
            se.setSource(QUrl.fromLocalFile(wav_path))
            se.setVolume(volume)
            se.play()
            self._sound_effects.append(se)
        except Exception as e:
            print(f"[LinuxX11Adapter] Sound cue playback failed: {e}")

    # ─── Topmost overlay ───────────────────────────────────────────────

    def make_window_topmost(self, window_handle) -> None:
        """No-op. Qt's WindowStaysOnTopHint is natively honored by X11 window managers."""
        pass

    # ─── Internal helpers ──────────────────────────────────────────────

    def _to_pynput_combo(self, combo: str) -> str:
        parts = [p.strip().lower() for p in combo.split("+")]
        translated = []
        for p in parts:
            if p in {"ctrl", "shift", "alt", "win", "cmd"}:
                translated.append(f"<{p}>")
            elif len(p) == 1:
                translated.append(p)
            else:
                translated.append(f"<{p}>")
        return "+".join(translated)

    def _parse_combo_keys(self, combo: str) -> set[str]:
        return {p.strip().lower() for p in combo.split("+")}

    def _normalize_key(self, key) -> str:
        if isinstance(key, pkb.Key):
            name = key.name
            if name in {"ctrl_l", "ctrl_r"}:
                return "ctrl"
            if name in {"shift_l", "shift_r", "shift"}:
                return "shift"
            if name in {"alt_l", "alt_r", "alt_gr"}:
                return "alt"
            if name in {"cmd_l", "cmd_r", "cmd"}:
                return "cmd"
            return name
        if isinstance(key, pkb.KeyCode):
            return (key.char or "").lower()
        return ""

    def _key_for(self, name: str):
        name = name.lower()
        special = {
            "ctrl": pkb.Key.ctrl,
            "shift": pkb.Key.shift,
            "alt": pkb.Key.alt,
            "win": pkb.Key.cmd,
            "cmd": pkb.Key.cmd,
            "enter": pkb.Key.enter,
            "tab": pkb.Key.tab,
            "esc": pkb.Key.esc,
            "space": pkb.Key.space,
            "backspace": pkb.Key.backspace,
            "delete": pkb.Key.delete,
            "up": pkb.Key.up,
            "down": pkb.Key.down,
            "left": pkb.Key.left,
            "right": pkb.Key.right,
            "home": pkb.Key.home,
            "end": pkb.Key.end,
            "pageup": pkb.Key.page_up,
            "pagedown": pkb.Key.page_down,
        }
        if name in special:
            return special[name]
        if len(name) == 1:
            return name
        if name.startswith("f") and name[1:].isdigit():
            return getattr(pkb.Key, name)
        raise ValueError(f"Unknown key: {name!r}")
