"""
PlatformAdapter — the interface every OS implementation satisfies.

This file IS the contributor doc for adding a new platform. If you implement
every method here, you have a working Clarity.V on your OS. Nothing else in
the codebase needs to change.

The interface is deliberately narrow. Five concerns:

  1. Hotkey listening   — register a key combo, get a callback when pressed/released
  2. Synthetic input    — send keys (Ctrl+V to paste, Ctrl+Enter to submit, etc.)
  3. Paste mechanism    — put text where the cursor is
  4. Audio cue playback — short WAV for activate/deactivate sounds
  5. Topmost overlay    — keep the glow bar on top of other windows

That's it. Adding a backend is small.

Conventions:
- All methods are synchronous. The audio capture thread runs separately.
- Methods may block briefly (a paste might take ~50ms). Never block for seconds.
- Errors should raise; the core handles them gracefully.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable


class PlatformAdapter(ABC):
    """Abstract base for platform-specific implementations.

    Each concrete subclass (WindowsAdapter, LinuxX11Adapter, MacOSAdapter)
    must implement all abstract methods. See `windows.py` for the reference
    implementation; other platforms should mirror its behavior as closely as
    the OS allows.
    """

    # ─── Identification ────────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable platform name. e.g. 'Windows', 'Linux/X11', 'macOS'."""

    # ─── Hotkeys (optional — voice flow doesn't require them) ─────────

    @abstractmethod
    def register_hotkey(
        self,
        combo: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None] | None = None,
        suppress: bool = True,
    ) -> None:
        """Register a global keyboard shortcut.

        Args:
            combo:       Key combination like "ctrl+shift+z" or "ctrl+space".
            on_press:    Called when the combo fires.
            on_release:  Called when the key is released. None = ignored.
                         Used to implement push-to-talk (hold = record).
            suppress:    If True, the original keystroke is swallowed (doesn't
                         reach the focused app). If False, it passes through.

        Implementations should normalize key names — `ctrl` and `control` and
        `Ctrl` all map to the same key.
        """

    @abstractmethod
    def unregister_all_hotkeys(self) -> None:
        """Remove every hotkey registered through this adapter. Called on shutdown."""

    # ─── Synthetic key events ─────────────────────────────────────────

    @abstractmethod
    def send_key_combo(self, combo: str) -> None:
        """Synthesize a keypress like 'ctrl+enter' or 'shift+tab'.

        Used by:
          - Voice commit (`enter` / `send` → Ctrl+Enter)
          - Mid-dictation commands (`tab` → Tab, `delete that` → Ctrl+Z, etc.)
          - Paste fallback (some adapters paste via Ctrl+V rather than clipboard).
        """

    # ─── Paste at cursor ──────────────────────────────────────────────

    @abstractmethod
    def paste_text(self, text: str) -> None:
        """Place `text` at the current cursor position in the focused app.

        Default strategy on most platforms: save existing clipboard, set
        clipboard to `text`, send Ctrl+V, restore clipboard. Implementations
        may choose a different strategy (e.g. macOS may use AppleScript;
        Wayland may use wl-clipboard) — what matters is the text appearing
        where the cursor is.

        Should handle multi-line text correctly (no truncation at \\n).
        """

    # ─── Audio cues ───────────────────────────────────────────────────

    @abstractmethod
    def play_sound(self, wav_path: str, volume: float = 1.0) -> None:
        """Play a short WAV file asynchronously.

        Must not block. Used for activate.wav / deactivate.wav cues.
        Failure to play should log but never crash — sound is non-critical.
        """

    # ─── Topmost overlay ──────────────────────────────────────────────

    @abstractmethod
    def make_window_topmost(self, window_handle) -> None:
        """Ensure the given window stays above all other windows.

        Args:
            window_handle: The OS-native window handle. On Windows that's
                an HWND (`int(win.winId())` from a Qt window). On X11 it's
                the X window ID. On macOS it's the NSWindow pointer.

        On most platforms Qt's `Qt.WindowStaysOnTopHint` is enough. Some
        OSes need re-assertion every few hundred ms to win against
        competing always-on-top apps; the platform can manage that
        internally if needed.
        """
