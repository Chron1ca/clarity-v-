"""
Windows adapter — Clarity.V's primary build target (v1.0).

Strategy:
- Hotkeys via `pynput.keyboard.GlobalHotKeys` (cross-platform on Win/Linux/Mac).
- Synthetic input via `pynput.keyboard.Controller`.
- Paste via clipboard (`pyperclip`) + Ctrl+V — survives multi-line text,
  preserves the user's previous clipboard.
- Audio cues via stdlib `winsound.PlaySound(..., SND_ASYNC)`.
- Topmost overlay via `win32gui.SetWindowPos(HWND_TOPMOST)`, re-asserted
  every 500 ms by a background timer (see `make_window_topmost`).
"""

from __future__ import annotations

import contextlib
import ctypes
import threading
import time
from collections.abc import Callable

import pyperclip
from pynput import keyboard as pkb

from clarity_v.platform._base import PlatformAdapter
from clarity_v.platform._win32_hotkeys import Win32HotkeyManager

# Windows-only imports, gracefully degraded if pywin32 is missing
try:
    import win32con
    import win32gui

    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False

try:
    import winsound

    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False


class WindowsAdapter(PlatformAdapter):
    """PlatformAdapter for Windows 10/11."""

    def __init__(self) -> None:
        self._hotkeys: dict[str, pkb.GlobalHotKeys] = {}
        self._listeners: list = []
        self._controller = pkb.Controller()
        self._topmost_timers: list = []
        # Win32 RegisterHotKey manager for press-only combos. Created
        # lazily so users with no hotkeys don't pay for the pump thread.
        self._win32_hotkeys: Win32HotkeyManager | None = None

    @property
    def name(self) -> str:
        return "Windows"

    # ─── Hotkeys ────────────────────────────────────────────────────────

    def register_hotkey(
        self,
        combo: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None] | None = None,
        suppress: bool = True,
    ) -> None:
        # PRESS-ONLY combos use Win32 RegisterHotKey via the manager —
        # OS-level, never absorbed by other apps' hooks, doesn't get
        # dropped when our process is "slow". The right tool for the
        # main hotkeys (toggle dictation, paste-last-dictation).
        if on_release is None:
            if self._win32_hotkeys is None:
                self._win32_hotkeys = Win32HotkeyManager()
            self._win32_hotkeys.register(combo, on_press)
            return

        # Push-to-talk: need press AND release. Win32 RegisterHotKey
        # doesn't notify on release, so PTT must use pynput.
        # (PTT is opt-in; users who don't use PTT pay no pynput cost.)
        keys_needed = self._parse_combo_keys(combo)
        combo_active = [False]
        release_timer = [None]

        def _fire_release():
            combo_active[0] = False
            on_release()

        def _on_press(key):
            normalized = self._normalize_key(key)
            if normalized in keys_needed:
                # Check hardware state of ALL required keys
                if all(self._is_key_pressed(k) for k in keys_needed):
                    if release_timer[0] is not None:
                        release_timer[0].cancel()
                        release_timer[0] = None
                    if not combo_active[0]:
                        combo_active[0] = True
                        on_press()

        def _on_release(key):
            normalized = self._normalize_key(key)
            if normalized in keys_needed:
                if combo_active[0] and not all(self._is_key_pressed(k) for k in keys_needed):
                    if release_timer[0] is not None:
                        release_timer[0].cancel()
                    # 100ms debounce to ignore auto-repeat phantom key-drops
                    release_timer[0] = threading.Timer(0.1, _fire_release)
                    release_timer[0].start()

        listener = pkb.Listener(on_press=_on_press, on_release=_on_release)
        listener.start()
        self._listeners.append(listener)

    def unregister_all_hotkeys(self) -> None:
        for gh in self._hotkeys.values():
            gh.stop()
        for listener in self._listeners:
            listener.stop()
        self._hotkeys.clear()
        self._listeners.clear()
        if self._win32_hotkeys is not None:
            self._win32_hotkeys.stop()
            self._win32_hotkeys = None

    # ─── Synthetic key events ──────────────────────────────────────────

    def send_key_combo(self, combo: str) -> None:
        keys = self._parse_combo_keys(combo)
        # Press modifiers first, then main key, then release in reverse.
        modifier_order = ["ctrl", "shift", "alt", "win", "cmd"]
        held = sorted(
            keys, key=lambda k: modifier_order.index(k) if k in modifier_order else 99
        )
        try:
            for k in held:
                self._controller.press(self._key_for(k))
            time.sleep(0.02)  # short delay so windows message loops (like Notepad's) register modifier state
            for k in reversed(held):
                self._controller.release(self._key_for(k))
        except Exception:
            # Best-effort release on failure — don't leave keys stuck.
            for k in held:
                with contextlib.suppress(Exception):
                    self._controller.release(self._key_for(k))
            raise

    # ─── Paste at cursor ───────────────────────────────────────────────

    def paste_text(self, text: str) -> None:
        """Paste `text` at the cursor without permanently disturbing the
        OS clipboard.

        Flow:
          1. Save the existing clipboard contents.
          2. Write `text` to clipboard.
          3. VERIFY the clipboard now reads back as `text` — retries with
             10 ms polls up to ~300 ms. If it never matches, abort the
             paste rather than send Ctrl+V with stale content.
             (This fixes the VSCode bug where stale clipboard contents
             got pasted instead of the dictation.)
          4. Send Ctrl+V.
          5. Wait ~400 ms for the target app to actually consume the
             clipboard, then restore the previous contents.

        Why the verify step matters: pyperclip.copy() returns before
        the Windows clipboard finishes synchronizing across all
        listeners. Apps that read clipboard on focus (VSCode does)
        can race ahead of the write and paste the stale content.
        """
        # 1. Save previous clipboard contents.
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = ""

        # 2. Write new text.
        try:
            pyperclip.copy(text)
        except Exception as e:
            print(f"[WindowsAdapter] Clipboard write failed: {e}")
            return

        # 3. Verify the clipboard caught up before pressing Ctrl+V.
        deadline = time.monotonic() + 0.3
        synced = False
        while time.monotonic() < deadline:
            try:
                if pyperclip.paste() == text:
                    synced = True
                    break
            except Exception:
                # Another process may hold the clipboard briefly; retry.
                pass
            time.sleep(0.01)

        if not synced:
            print(
                "[WindowsAdapter] Clipboard did not sync within 300 ms — "
                "ABORTING paste to avoid stale-content paste. "
                "Use the paste-last keybind to re-paste the dictation."
            )
            # Restore previous content before bailing out.
            with contextlib.suppress(Exception):
                pyperclip.copy(previous)
            return

        # 4. Press Ctrl+V.
        self.send_key_combo("ctrl+v")

        # 5. Restore previous clipboard after the target app has had
        # plenty of time to consume our paste. 400 ms is conservative;
        # most apps consume within 50-100 ms.
        def _restore():
            time.sleep(0.4)
            with contextlib.suppress(Exception):
                pyperclip.copy(previous)

        threading.Thread(target=_restore, daemon=True).start()

    # ─── Audio cues ────────────────────────────────────────────────────

    def play_sound(self, wav_path: str, volume: float = 1.0) -> None:
        # On Windows, winsound is 100% reliable, thread-safe, and plays from background threads.
        # QSoundEffect fails silently when called from threads without a running Qt event loop.
        if HAS_WINSOUND:
            try:
                winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
            except Exception:
                pass

        try:
            from PySide6.QtMultimedia import QSoundEffect
            from PySide6.QtCore import QUrl
            if not hasattr(self, "_sound_effects"):
                self._sound_effects = []
            
            # Clean up finished sound effects
            self._sound_effects = [se for se in self._sound_effects if not se.isPlaying()]
            
            se = QSoundEffect()
            se.setSource(QUrl.fromLocalFile(wav_path))
            se.setVolume(volume)
            se.play()
            self._sound_effects.append(se)
        except Exception:
            pass

    # ─── Topmost overlay ───────────────────────────────────────────────

    def make_window_topmost(self, window_handle) -> None:
        """Ensure window stays above all others.

        Strategy (most-aggressive first):

        1. Set the WS_EX_TOPMOST extended window style — a "sticky"
           flag that survives most Z-order changes.
        2. SetWindowPos(HWND_TOPMOST) once at registration time.
        3. Re-assert every 200 ms on a daemon thread. Apps that
           themselves use HWND_TOPMOST can still beat us, but only
           briefly — the next 200 ms tick puts us back on top.

        Re-assertion uses SWP_NOACTIVATE so we never steal focus from
        the focused window — important for typing into other apps
        while the glow bar is visible.
        """
        if not HAS_PYWIN32:
            return  # Qt's WindowStaysOnTopHint is the fallback.

        hwnd = int(window_handle)

        # 1. Set the WS_EX_TOPMOST extended style on the window itself.
        try:
            GWL_EXSTYLE = -20
            current = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, current | win32con.WS_EX_TOPMOST
            )
        except Exception:
            pass

        flags = (
            win32con.SWP_NOMOVE
            | win32con.SWP_NOSIZE
            | win32con.SWP_NOACTIVATE
            | win32con.SWP_SHOWWINDOW
        )

        # 2. Initial assertion.
        with contextlib.suppress(Exception):
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)

        # 3. Re-assert on a 200 ms cadence. Cheaper than blind every
        # frame, fast enough to recover from other always-on-top apps
        # winning Z-order briefly.
        def _reassert():
            while True:
                try:
                    win32gui.SetWindowPos(
                        hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags
                    )
                except Exception:
                    return  # Window destroyed; stop trying.
                time.sleep(0.2)

        t = threading.Thread(target=_reassert, daemon=True)
        t.start()
        self._topmost_timers.append(t)

    # ─── Internal helpers ──────────────────────────────────────────────

    def _to_pynput_combo(self, combo: str) -> str:
        """Translate 'ctrl+shift+z' → '<ctrl>+<shift>+z' for pynput."""
        parts = [p.strip().lower() for p in combo.split("+")]
        translated = []
        for p in parts:
            if p in {"ctrl", "shift", "alt", "win", "cmd"}:
                translated.append(f"<{p}>")
            elif len(p) == 1:
                translated.append(p)
            else:
                # Function keys etc. — pynput uses <f1>, <enter>, <space>.
                translated.append(f"<{p}>")
        return "+".join(translated)

    def _parse_combo_keys(self, combo: str) -> set:
        return {p.strip().lower() for p in combo.split("+")}

    def _is_key_pressed(self, name: str) -> bool:
        """Query the physical hardware state of a key via Win32 API."""
        import ctypes
        vk = 0
        special = {
            "ctrl": 0x11, # VK_CONTROL
            "shift": 0x10, # VK_SHIFT
            "alt": 0x12, # VK_MENU
            "win": 0x5B, # VK_LWIN
            "cmd": 0x5B,
            "enter": 0x0D,
            "tab": 0x09,
            "esc": 0x1B,
            "space": 0x20,
            "backspace": 0x08,
            "delete": 0x2E,
        }
        if name in special:
            vk = special[name]
        elif len(name) == 1:
            vk = ord(name.upper())
        if not vk:
            return False
        # High bit is set if key is currently down
        return (ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000) != 0

    def _normalize_key(self, key) -> str:
        """pynput Key/KeyCode → lowercase string matching our combo format."""
        if isinstance(key, pkb.Key):
            name = key.name
            if name in {"ctrl_l", "ctrl_r"}:
                return "ctrl"
            if name in {"shift", "shift_l", "shift_r"}:
                return "shift"
            if name in {"alt_l", "alt_r", "alt_gr"}:
                return "alt"
            if name in {"cmd", "cmd_l", "cmd_r"}:
                return "cmd"
            return name
        if isinstance(key, pkb.KeyCode):
            return (key.char or "").lower()
        return ""

    def _key_for(self, name: str):
        """Map combo-name like 'ctrl' / 'enter' / 'v' to a pynput key."""
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
        # f1-f24
        if name.startswith("f") and name[1:].isdigit():
            return getattr(pkb.Key, name)
        raise ValueError(f"Unknown key: {name!r}")
