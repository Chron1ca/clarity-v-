"""
PresenceApp — composes the glow bar + tray + Qt event loop.

Use this when you want the full visual layer running. For headless use
(e.g., tests, the dictation engine without UI), import the engine
directly without touching presence/.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from PySide6.QtWidgets import QApplication

from clarity_v.presence.colors import GlowColors
from clarity_v.presence.overlay import GlowBar
from clarity_v.presence.start_stop_button import StartStopButton
from clarity_v.presence.tray import ClarityTray
from clarity_v.state import StateManager


class PresenceApp:
    """The Qt-rooted visual layer of Clarity.V.

    Constructs (or reuses) a QApplication, then sets up the glow bar
    and tray icon. `start()` blocks on the Qt event loop.

    The state_manager argument is shared with the dictation engine —
    state transitions in the engine propagate here automatically.
    """

    def __init__(
        self,
        state_manager: StateManager,
        colors: GlowColors | None = None,
        show_bar: bool = True,
        show_tray: bool = True,
        bar_height: int = 60,
        bar_brightness: float = 0.75,
        bar_position: str = "top",
        bar_freeform_x: int = 0,
        bar_freeform_y: int = 0,
        show_start_stop_button: bool = False,
        start_stop_button_locked: bool = False,
        start_stop_button_size: int = 56,
        start_stop_button_x: int = -1,
        start_stop_button_y: int = -1,
        on_toggle_dictation: Callable[[], str] | None = None,
        on_button_moved: Callable[[int, int], None] | None = None,
        on_button_locked: Callable[[bool], None] | None = None,
        on_button_hidden: Callable[[], None] | None = None,
        on_pause_resume: Callable[[], None] | None = None,
        on_settings: Callable[[], None] | None = None,
        on_about: Callable[[], None] | None = None,
        on_toggle_glow_bar: Callable[[], None] | None = None,
        on_toggle_button: Callable[[], None] | None = None,
        on_copy_last_transcript: Callable[[], None] | None = None,
    ) -> None:
        self.state_manager = state_manager
        self.colors = colors or GlowColors()
        self._on_copy_last_transcript = on_copy_last_transcript
        self._start_stop_button_locked = start_stop_button_locked
        self._on_button_locked = on_button_locked

        # Reuse the existing QApplication if there is one (lets the engine
        # embed presence inside a host app), else create our own.
        existing = QApplication.instance()
        if existing is None:
            self._app = QApplication(sys.argv)
            self._owns_app = True
        else:
            self._app = existing
            self._owns_app = False

        from pathlib import Path
        from PySide6.QtGui import QIcon
        icon_path = Path(__file__).resolve().parent.parent.parent.parent / "cv_logo.ico"
        if icon_path.exists():
            self._app.setWindowIcon(QIcon(str(icon_path)))

        # Don't quit when the bar is closed — the tray drives lifecycle.
        self._app.setQuitOnLastWindowClosed(False)

        self.bar: GlowBar | None = None
        self.tray: ClarityTray | None = None
        self.start_stop_button: StartStopButton | None = None

        self._on_toggle_dictation = on_toggle_dictation
        self._on_button_moved = on_button_moved
        self._on_button_hidden = on_button_hidden
        self._on_pause_resume = on_pause_resume
        self._on_settings = on_settings
        self._on_about = on_about
        self._on_toggle_glow_bar = on_toggle_glow_bar
        self._on_toggle_button = on_toggle_button

        self._build_ui(
            show_bar=show_bar,
            show_tray=show_tray,
            bar_height=bar_height,
            bar_brightness=bar_brightness,
            bar_position=bar_position,
            bar_freeform_x=bar_freeform_x,
            bar_freeform_y=bar_freeform_y,
            show_start_stop_button=show_start_stop_button,
            start_stop_button_locked=self._start_stop_button_locked,
            start_stop_button_size=start_stop_button_size,
            start_stop_button_x=start_stop_button_x,
            start_stop_button_y=start_stop_button_y,
        )

    def _build_ui(
        self,
        show_bar: bool,
        show_tray: bool,
        bar_height: int,
        bar_brightness: float,
        bar_position: str,
        bar_freeform_x: int,
        bar_freeform_y: int,
        show_start_stop_button: bool,
        start_stop_button_size: int,
        start_stop_button_x: int,
        start_stop_button_y: int,
        start_stop_button_locked: bool = False,
    ) -> None:
        if show_bar:
            self.bar = GlowBar(
                self.state_manager,
                self.colors,
                height=bar_height,
                brightness=bar_brightness,
                position=bar_position,
                freeform_x=bar_freeform_x,
                freeform_y=bar_freeform_y,
            )
        if show_start_stop_button and self._on_toggle_dictation is not None:
            # -1 sentinel = use widget's bottom-right default.
            x = start_stop_button_x if start_stop_button_x >= 0 else None
            y = start_stop_button_y if start_stop_button_y >= 0 else None
            self.start_stop_button = StartStopButton(
                self.state_manager,
                on_toggle=self._on_toggle_dictation,
                colors=self.colors,
                size=start_stop_button_size,
                brightness=bar_brightness,
                x=x,
                y=y,
                on_position_changed=self._on_button_moved,
                on_toggle_button=self._on_toggle_button,
                on_pause_resume=self._on_pause_resume,
                on_settings=self._on_settings,
                on_about=self._on_about,
                on_quit=self.quit,
                on_toggle_glow_bar=self._on_toggle_glow_bar,
                locked=start_stop_button_locked,
                on_lock_changed=self._on_button_locked,
            )

        if show_tray:
            self.tray = ClarityTray(
                self.state_manager,
                self.colors,
                on_pause_resume=self._on_pause_resume,
                on_settings=self._on_settings,
                on_about=self._on_about,
                on_quit=self.quit,
                on_toggle_glow_bar=self._on_toggle_glow_bar,
                on_toggle_button=self._on_toggle_button,
                on_copy_last_transcript=self._on_copy_last_transcript,
            )

    def reload_ui(self, settings) -> None:
        """Live-reload UI elements based on new settings without dropping Qt loop."""
        # 1. Close existing visual elements
        if self.bar is not None:
            self.bar.close()
            self.bar = None
        if self.start_stop_button is not None:
            self.start_stop_button.close()
            self.start_stop_button = None
        if self.tray is not None:
            self.tray.hide()
            self.tray = None

        # 2. Re-read colors
        from clarity_v.app import _make_colors  # dynamic import to avoid circular dependency
        self.colors = _make_colors(settings)
        self._start_stop_button_locked = settings.start_stop_button_locked

        # 3. Rebuild widgets
        self._build_ui(
            show_bar=settings.show_glow_bar,
            show_tray=settings.show_tray_icon,
            bar_height=settings.glow_bar_height,
            bar_brightness=settings.glow_bar_brightness,
            bar_position=settings.glow_bar_position,
            bar_freeform_x=settings.glow_bar_x,
            bar_freeform_y=settings.glow_bar_y,
            show_start_stop_button=settings.show_start_stop_button,
            start_stop_button_size=settings.start_stop_button_size,
            start_stop_button_x=settings.start_stop_button_x,
            start_stop_button_y=settings.start_stop_button_y,
            start_stop_button_locked=settings.start_stop_button_locked,
        )

        # 4. Show newly built elements
        self.show()

    # ─── Lifecycle ────────────────────────────────────────────────────

    def show(self) -> None:
        """Make the visual elements visible (does not block)."""
        if self.bar is not None:
            self.bar.show()
        if self.tray is not None:
            self.tray.show()
        if self.start_stop_button is not None:
            self.start_stop_button.show()

    def start(self) -> int:
        """Show the UI and block on the Qt event loop. Returns exit code.

        Only call this on the main thread. If your host app already
        runs a Qt event loop, just call `show()` and let your loop run.
        """
        self.show()
        return self._app.exec()

    def quit(self) -> None:
        if self.bar is not None:
            self.bar.close()
        if self.tray is not None:
            self.tray.hide()
        if self.start_stop_button is not None:
            self.start_stop_button.close()
            
        # Close any open SettingsDialog to prevent blocking exit
        try:
            from PySide6.QtWidgets import QApplication
            from clarity_v.settings.window import SettingsDialog
            for w in QApplication.topLevelWidgets():
                if isinstance(w, SettingsDialog):
                    w.close()
        except Exception as e:
            print(f"[PresenceApp] Error closing settings dialog on quit: {e}")

        self._app.quit()
