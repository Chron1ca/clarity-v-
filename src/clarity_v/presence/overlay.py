"""
GlowBar — a thin, always-on-top, click-through bar at the top of the screen.

Visual indicator of the engine's current state. Subscribes to a
StateManager: every state change updates the bar's color and intensity.

Design choices:
- Borderless, frameless, no taskbar entry, no focus stealing.
- Click-through: mouse events pass through to whatever's behind it
  (Wayland excluded — see PlatformAdapter notes).
- Configurable height (default 6 px) and color-per-state (see colors.py).
- Hideable: settings can disable rendering entirely.

The bar always exists at top: configurable position is a v1.1 feature.
"""

from __future__ import annotations

import contextlib

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

from clarity_v.presence.colors import GlowColors
from clarity_v.state import State, StateManager


class GlowBar(QWidget):
    """The always-on-top color bar.

    Construction does NOT show the window — call `show()`.
    Tearing down is just `close()`; the StateManager subscription
    auto-detaches when the widget is destroyed.
    """

    # Signal used to marshal state changes from the audio/state thread
    # onto the Qt main thread (Qt widgets are not thread-safe).
    _state_changed = Signal(object)

    def __init__(
        self,
        state_manager: StateManager,
        colors: GlowColors | None = None,
        height: int = 60,
        brightness: float = 0.75,
        position: str = "top",
        freeform_x: int = 0,
        freeform_y: int = 0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state_manager = state_manager
        self._colors = colors or GlowColors()
        self._bar_height = height
        self._brightness = max(0.0, min(1.0, brightness))
        self._position = position
        self._freeform_x = freeform_x
        self._freeform_y = freeform_y
        self._current_color = self._color_for(self._state_manager.state)

        # Window flags — frameless, always on top, no taskbar, tool
        # window (so it doesn't steal focus), and crucially
        # WindowTransparentForInput so the entire window passes mouse
        # events through to whatever's behind it. The widget-level
        # WA_TransparentForMouseEvents attribute alone is not enough on
        # Windows for an OS-wide overlay; the window flag is.
        flags = (
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Position the bar according to the configured setting.
        # "top" / "bottom" snap to the primary screen edge; "freeform"
        # places it at (freeform_x, freeform_y) and the user owns sizing.
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geom = screen.geometry()
            if self._position == "bottom":
                self.setGeometry(
                    geom.x(),
                    geom.y() + geom.height() - self._bar_height,
                    geom.width(),
                    self._bar_height,
                )
            elif self._position == "left":
                self.setGeometry(
                    geom.x(),
                    geom.y(),
                    self._bar_height,
                    geom.height(),
                )
            elif self._position == "right":
                self.setGeometry(
                    geom.x() + geom.width() - self._bar_height,
                    geom.y(),
                    self._bar_height,
                    geom.height(),
                )
            elif self._position == "freeform":
                self.setGeometry(
                    self._freeform_x,
                    self._freeform_y,
                    geom.width(),
                    self._bar_height,
                )
            else:  # "top" (default)
                self.setGeometry(
                    geom.x(),
                    geom.y(),
                    geom.width(),
                    self._bar_height,
                )

        # Wire the cross-thread signal to a Qt slot.
        self._state_changed.connect(self._on_state_changed_qt)
        # Subscribe to state events.
        self._subscriber = self._on_state_event
        self._state_manager.subscribe(self._subscriber)

        # Periodic topmost re-assertion to win against other always-on-top
        # apps. 500 ms is the same cadence the platform adapter uses.
        self._reassert_timer = QTimer(self)
        self._reassert_timer.setInterval(500)
        self._reassert_timer.timeout.connect(self._reassert_topmost)
        self._reassert_timer.start()

    # ─── State-change pipeline ────────────────────────────────────────

    def _on_state_event(self, state: State, info: dict) -> None:
        """StateManager subscriber — runs on whatever thread fired.

        Marshals to Qt's main thread via a queued signal.
        """
        self._state_changed.emit(state)

    def _on_state_changed_qt(self, state: State) -> None:
        """Runs on Qt main thread; safe to touch widgets."""
        self._current_color = self._color_for(state)
        self.update()  # schedule a repaint

    def _color_for(self, state: State) -> QColor:
        """Apply the brightness multiplier to the state's configured color.

        Brightness only scales the alpha channel — RGB stays as the user
        configured it. So brightness=0.5 means half-as-opaque, not
        a darker color.
        """
        r, g, b, a = self._colors.for_state(state)
        a = int(a * self._brightness)
        return QColor(r, g, b, max(0, min(255, a)))

    # ─── Painting ─────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        """Paint the glow.

        The bar is rendered as a position-aware multi-stop linear gradient
        so it reads as a glow at the screen edge fading into transparency,
        not as a flat rectangle of color. The glow is brightest at the
        edge of the screen the bar sits against; stops at 0.10, 0.25,
        0.40, 0.60, 0.80 of the bar's height produce a soft falloff.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        color = self._current_color
        r, g, b = color.red(), color.green(), color.blue()
        base_alpha = color.alpha()

        # Position-aware gradient direction. For "top" (default) and
        # "freeform" the glow lives at the top of the widget and fades
        # downward; for "bottom" the glow lives at the bottom and fades
        # upward — both put the brightest pixels against the screen edge.
        if self._position == "bottom":
            grad = QLinearGradient(0, rect.height(), 0, 0)
        elif self._position == "left":
            grad = QLinearGradient(0, 0, rect.width(), 0)
        elif self._position == "right":
            grad = QLinearGradient(rect.width(), 0, 0, 0)
        else:
            grad = QLinearGradient(0, 0, 0, rect.height())

        grad.setColorAt(0.00, QColor(r, g, b, base_alpha))
        grad.setColorAt(0.10, QColor(r, g, b, int(base_alpha * 0.60)))
        grad.setColorAt(0.25, QColor(r, g, b, int(base_alpha * 0.30)))
        grad.setColorAt(0.40, QColor(r, g, b, int(base_alpha * 0.12)))
        grad.setColorAt(0.60, QColor(r, g, b, int(base_alpha * 0.04)))
        grad.setColorAt(0.80, QColor(r, g, b, 0))
        grad.setColorAt(1.00, QColor(r, g, b, 0))

        painter.fillRect(rect, grad)

    # ─── Topmost re-assertion ─────────────────────────────────────────

    def _reassert_topmost(self) -> None:
        """Re-raise the window. Some always-on-top apps will steal Z-order
        otherwise. This is the same dance the WindowsAdapter does at
        the OS level — Qt's WindowStaysOnTopHint is best-effort."""
        with contextlib.suppress(Exception):
            self.raise_()

    # ─── Cleanup ──────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        with contextlib.suppress(Exception):
            self._state_manager.unsubscribe(self._subscriber)
        self._reassert_timer.stop()
        super().closeEvent(event)
