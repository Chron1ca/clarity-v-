"""
Win32 RegisterHotKey wrapper — OS-level global hotkeys.

Why this exists: pynput's global keyboard hook works most of the time
but has two failure modes that bite Clarity.V in real use:

  1. Windows silently drops "slow" low-level hooks. If the callback
     takes more than a few hundred ms (or if any hook in the chain
     does), the OS removes ALL hooks. Other apps coming online with
     their own hooks can also evict ours.
  2. Apps with focus + their own keyboard handling can absorb the
     keystroke before it reaches the global hook chain.

`RegisterHotKey` from the Win32 API solves both. It's a system-wide
registration: the OS itself matches the combo against its internal
table and posts WM_HOTKEY messages to the owning thread. No callback
chain, no per-app hooks, no "slow handler" eviction. The only failure
mode is duplicate registration — if another app already registered
the same combo, ours fails with a clear error.

Each combo runs the callback on a dedicated message-pump thread. The
callback is invoked synchronously from the thread, so don't do
heavy work in it — schedule onto a worker thread instead.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
from collections.abc import Callable

# Win32 constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000  # don't fire repeatedly while held

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

# Modifier string → flag map.
_MODIFIER_MAP = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "alt": MOD_ALT,
    "win": MOD_WIN,
    "cmd": MOD_WIN,
    "super": MOD_WIN,
}

# Special-key string → VK code map. Common ones; extend as needed.
_VK_MAP = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
}
# Function keys F1-F24
for i in range(1, 25):
    _VK_MAP[f"f{i}"] = 0x6F + i  # F1 = 0x70


def _parse_combo(combo: str) -> tuple[int, int]:
    """'ctrl+shift+v' → (MOD_CONTROL | MOD_SHIFT, 0x56)."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"Empty hotkey combo: {combo!r}")
    mods = 0
    main = None
    for p in parts:
        if p in _MODIFIER_MAP:
            mods |= _MODIFIER_MAP[p]
        else:
            if main is not None:
                raise ValueError(
                    f"Hotkey {combo!r}: multiple main keys ({main!r}, {p!r})"
                )
            main = p
    if main is None:
        raise ValueError(f"Hotkey {combo!r}: no main key")
    # Resolve VK code
    if main in _VK_MAP:
        vk = _VK_MAP[main]
    elif len(main) == 1:
        ch = main.upper()
        vk = ord(ch)
    else:
        raise ValueError(f"Hotkey {combo!r}: unknown key {main!r}")
    return mods | MOD_NOREPEAT, vk


class Win32HotkeyManager:
    """Manages OS-level Win32 hotkey registrations.

    Each manager runs its own message-pump thread. Register hotkeys
    with `register(combo, callback)`. Unregister all with `stop()`.

    Thread safety: callbacks are invoked on the manager's pump thread,
    not the caller's thread. The callback should not block — schedule
    heavy work onto another thread.
    """

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._registrations: dict[int, tuple[str, Callable[[], None]]] = {}
        self._next_id: int = 1
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._stopping = False
        # Pending registrations queued before the thread is up
        self._pending: list = []
        self._lock = threading.Lock()

    # ─── Public API ───────────────────────────────────────────────────

    def register(
        self,
        combo: str,
        callback: Callable[[], None],
    ) -> bool:
        """Register `combo` as a global hotkey firing `callback` on press.

        Returns True if registration succeeded, False if the combo is
        already in use by another process (or if registration failed
        for any other reason — see stderr).
        """
        mods, vk = _parse_combo(combo)

        # Start the thread on first register.
        with self._lock:
            if self._thread is None:
                self._start_thread()
            self._ready.wait(timeout=2.0)
            if self._thread_id is None:
                print("[Win32Hotkeys] Pump thread failed to start.")
                return False

        # Schedule the actual RegisterHotKey call onto the pump thread.
        # Win32 hotkey registration must happen on the thread that runs
        # GetMessage — otherwise WM_HOTKEY can't reach us.
        result = {"ok": False, "id": None}
        done = threading.Event()

        def do_register():
            try:
                hid = self._next_id
                self._next_id += 1
                ok = self._user32.RegisterHotKey(None, hid, mods, vk)
                if ok:
                    self._registrations[hid] = (combo, callback)
                    result["ok"] = True
                    result["id"] = hid
                else:
                    err = self._kernel32.GetLastError()
                    print(
                        f"[Win32Hotkeys] RegisterHotKey {combo!r} failed "
                        f"(GetLastError={err}). Likely already in use."
                    )
            finally:
                done.set()

        self._post_to_pump(do_register)
        done.wait(timeout=2.0)
        return result["ok"]

    def stop(self) -> None:
        """Unregister all hotkeys and stop the pump thread."""
        with self._lock:
            if self._thread is None:
                return
            self._stopping = True
            for hid in list(self._registrations.keys()):
                self._post_to_pump(lambda h=hid: self._user32.UnregisterHotKey(None, h))
            # Wake the pump so it exits its loop.
            if self._thread_id:
                self._user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(timeout=2.0)
            self._thread = None
            self._thread_id = None
            self._registrations.clear()

    # ─── Pump thread ──────────────────────────────────────────────────

    def _start_thread(self) -> None:
        self._thread = threading.Thread(
            target=self._pump,
            name="Win32HotkeyPump",
            daemon=True,
        )
        self._thread.start()

    def _pump(self) -> None:
        """Win32 message pump. Owns the hotkey registrations."""
        self._thread_id = self._kernel32.GetCurrentThreadId()
        self._ready.set()

        msg = wt.MSG()
        # GetMessage blocks until a message arrives. Hotkey presses
        # arrive as WM_HOTKEY; we also use PostThreadMessage to inject
        # callbacks (custom messages) and WM_QUIT to exit.
        # 0x0400 (WM_USER) custom messages carry function pointers via
        # a side-channel queue (_pending).
        while True:
            ret = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                # WM_QUIT or error
                break

            if msg.message == WM_HOTKEY:
                hid = msg.wParam
                entry = self._registrations.get(hid)
                if entry is not None:
                    combo, callback = entry
                    try:
                        callback()
                    except Exception as e:
                        print(
                            f"[Win32Hotkeys] callback {combo!r} raised: "
                            f"{type(e).__name__}: {e}"
                        )

            elif msg.message == 0x0400:  # WM_USER — drain pending fns
                # Pop and run pending callables in order.
                while True:
                    with self._lock:
                        if not self._pending:
                            break
                        fn = self._pending.pop(0)
                    try:
                        fn()
                    except Exception as e:
                        print(
                            f"[Win32Hotkeys] pending fn raised: {type(e).__name__}: {e}"
                        )

            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))

    def _post_to_pump(self, fn: Callable[[], None]) -> None:
        """Queue a function to run on the pump thread."""
        with self._lock:
            self._pending.append(fn)
        if self._thread_id is not None:
            self._user32.PostThreadMessageW(self._thread_id, 0x0400, 0, 0)
