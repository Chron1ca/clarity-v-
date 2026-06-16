"""
System tray icon + context menu.

Shows the engine state at a glance via a colored icon. Right-click menu:
  - Pause/Resume
  - Settings
  - About
  - Quit
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QPainter,
    QPixmap,
    QPainterPath,
    QLinearGradient,
    QPen,
)
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from clarity_v.presence.colors import GlowColors
from clarity_v.state import State, StateManager


def _make_icon(color: tuple[int, int, int, int], size: int = 32) -> QIcon:
    """Render the custom CV logo icon with the V changing color according to state."""
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))  # transparent background
    
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    
    pad = 2
    logo_w = size - 2 * pad
    logo_h = size - 2 * pad
    logo_x = pad
    logo_y = pad

    # Create the outer "C" crystal path
    c_path = QPainterPath()
    c_path.moveTo(logo_x + logo_w * 0.15, logo_y + logo_h * 0.05)
    c_path.lineTo(logo_x + logo_w * 0.85, logo_y + logo_h * 0.05)
    c_path.lineTo(logo_x + logo_w * 0.99, logo_y + logo_h * 0.25)
    c_path.lineTo(logo_x + logo_w * 0.76, logo_y + logo_h * 0.25)
    c_path.lineTo(logo_x + logo_w * 0.24, logo_y + logo_h * 0.25)
    c_path.lineTo(logo_x + logo_w * 0.50, logo_y + logo_h * 0.77)
    c_path.lineTo(logo_x + logo_w * 0.725, logo_y + logo_h * 0.32)
    c_path.lineTo(logo_x + logo_w * 0.96, logo_y + logo_h * 0.32)
    c_path.lineTo(logo_x + logo_w * 0.50, logo_y + logo_h * 0.98)
    c_path.lineTo(logo_x + logo_w * 0.01, logo_y + logo_h * 0.25)
    c_path.closeSubpath()

    # Fill the "C" with purple crystal gradient
    grad = QLinearGradient(logo_x + logo_w / 2, logo_y, logo_x + logo_w / 2, logo_y + logo_h)
    grad.setColorAt(0.0, QColor(168, 85, 247, 245))  # vibrant purple
    grad.setColorAt(1.0, QColor(76, 29, 149, 255))   # deep purple
    p.setBrush(grad)

    # Draw crystal border (simulates bevel outline lit from top-down)
    c_pen_grad = QLinearGradient(logo_x + logo_w / 2, logo_y, logo_x + logo_w / 2, logo_y + logo_h)
    c_pen_grad.setColorAt(0.0, QColor(240, 220, 255, 255))
    c_pen_grad.setColorAt(0.3, QColor(216, 180, 254, 255))
    c_pen_grad.setColorAt(1.0, QColor(110, 68, 180, 255))
    p.setPen(QPen(c_pen_grad, 1.2))
    p.drawPath(c_path)

    # Retrieve active state color
    r, g, b, _ = color
    
    # Fill the inner "V" with 3D gradient matching active state
    v_grad = QLinearGradient(logo_x + logo_w / 2, logo_y + logo_h * 0.25, logo_x + logo_w / 2, logo_y + logo_h * 0.77)
    v_grad.setColorAt(0.0, QColor(r, g, b, 255))
    v_grad.setColorAt(1.0, QColor(max(0, r - 60), max(0, g - 60), max(0, b - 60), 255))
    p.setBrush(v_grad)

    # Create dynamic "V" path
    v_path = QPainterPath()
    v_path.moveTo(logo_x + logo_w * 0.24, logo_y + logo_h * 0.25)
    v_path.lineTo(logo_x + logo_w * 0.50, logo_y + logo_h * 0.77)
    v_path.lineTo(logo_x + logo_w * 0.76, logo_y + logo_h * 0.25)
    v_path.lineTo(logo_x + logo_w * 0.64, logo_y + logo_h * 0.25)
    v_path.lineTo(logo_x + logo_w * 0.50, logo_y + logo_h * 0.53)
    v_path.lineTo(logo_x + logo_w * 0.36, logo_y + logo_h * 0.25)
    v_path.closeSubpath()

    # Stroke the "V" with gradient
    v_pen_grad = QLinearGradient(logo_x + logo_w / 2, logo_y + logo_h * 0.25, logo_x + logo_w / 2, logo_y + logo_h * 0.77)
    v_pen_grad.setColorAt(0.0, QColor(min(255, r + 60), min(255, g + 60), min(255, b + 60), 255))
    v_pen_grad.setColorAt(1.0, QColor(max(0, r - 20), max(0, g - 20), max(0, b - 20), 255))
    p.setPen(QPen(v_pen_grad, 1.0))
    p.drawPath(v_path)

    p.end()
    return QIcon(pix)


class ClarityTray(QSystemTrayIcon):
    """System tray icon that mirrors engine state.

    Construction does NOT install the icon — call `show()`.
    """

    # Cross-thread state propagation (same pattern as the glow bar).
    _state_changed = Signal(object)

    def __init__(
        self,
        state_manager: StateManager,
        colors: GlowColors | None = None,
        on_pause_resume: Callable[[], None] | None = None,
        on_settings: Callable[[], None] | None = None,
        on_about: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        on_toggle_glow_bar: Callable[[], None] | None = None,
        on_toggle_button: Callable[[], None] | None = None,
        on_copy_last_transcript: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state_manager = state_manager
        self._colors = colors or GlowColors()
        self._on_pause_resume = on_pause_resume
        self._on_settings = on_settings
        self._on_about = on_about
        self._on_quit = on_quit
        self._on_toggle_glow_bar = on_toggle_glow_bar
        self._on_toggle_button = on_toggle_button
        self._on_copy_last_transcript = on_copy_last_transcript
        self._paused = False

        self.setIcon(_make_icon(self._colors.for_state(self._state_manager.state)))
        self.setToolTip(f"Clarity.V — {self._state_manager.state.value}")
        self._build_menu()

        self.activated.connect(self._on_activated)

        self._state_changed.connect(self._on_state_changed_qt)
        self._subscriber = self._on_state_event
        self._state_manager.subscribe(self._subscriber)

    # ─── Menu ─────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        # The menu is owned by the tray icon (self). Each QAction is
        # parented to the menu so Win11 reliably surfaces every entry
        # on right-click; unparented actions can drop from the popup.
        self._menu = QMenu()
        self._pause_action = QAction("Pause", self._menu)
        self._pause_action.triggered.connect(self._handle_pause_resume)
        self._menu.addAction(self._pause_action)

        self._menu.addSeparator()

        copy_action = QAction("Copy Last Transcript", self._menu)
        copy_action.triggered.connect(
            lambda: self._on_copy_last_transcript() if self._on_copy_last_transcript else None
        )
        self._menu.addAction(copy_action)

        self._menu.addSeparator()

        self._toggle_bar_action = QAction("Toggle Glow Bar", self._menu)
        self._toggle_bar_action.triggered.connect(
            lambda: self._on_toggle_glow_bar() if hasattr(self, '_on_toggle_glow_bar') and self._on_toggle_glow_bar else None
        )
        self._menu.addAction(self._toggle_bar_action)

        self._toggle_button_action = QAction("Toggle Float Button", self._menu)
        self._toggle_button_action.triggered.connect(
            lambda: self._on_toggle_button() if hasattr(self, '_on_toggle_button') and self._on_toggle_button else None
        )
        self._menu.addAction(self._toggle_button_action)

        self._menu.addSeparator()

        settings_action = QAction("Settings…", self._menu)
        settings_action.triggered.connect(
            lambda: self._on_settings() if self._on_settings else None
        )
        self._menu.addAction(settings_action)

        about_action = QAction("About Clarity.V", self._menu)
        about_action.triggered.connect(
            lambda: self._on_about() if self._on_about else None
        )
        self._menu.addAction(about_action)

        self._menu.addSeparator()

        quit_action = QAction("Quit Clarity.V", self._menu)
        quit_action.triggered.connect(
            lambda: self._on_quit() if self._on_quit else None
        )
        self._menu.addAction(quit_action)

        self.setContextMenu(self._menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            if self._on_settings:
                self._on_settings()

    def _handle_pause_resume(self) -> None:
        self._paused = not self._paused
        self._pause_action.setText("Resume" if self._paused else "Pause")
        if self._on_pause_resume:
            self._on_pause_resume()

    # ─── State pipeline ───────────────────────────────────────────────

    def _on_state_event(self, state: State, info: dict) -> None:
        self._state_changed.emit(state)

    def _on_state_changed_qt(self, state: State) -> None:
        self.setIcon(_make_icon(self._colors.for_state(state)))
        self.setToolTip(f"Clarity.V — {state.value}")
