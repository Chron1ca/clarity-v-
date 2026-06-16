"""
Floating start/stop button — mouse-driven dictation control.

A small circular widget that floats over everything. Left-click toggles
dictation (start if idle, stop if recording). Color mirrors engine
state (same palette as the glow bar). Draggable with the mouse.
Right-click menu to hide or snap to a screen edge.

This is the fourth way to control dictation, alongside:
  - voice (wake word + silence/wake-refire)
  - push-to-talk (hold a key)
  - keybind toggle (press once start, press once stop)

Position is persisted via the Settings model (start_stop_button_x/y).
The widget calls the on_toggle callback whenever the user clicks it;
the engine's `toggle_recording()` is the canonical target.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPen,
    QPainterPath,
    QLinearGradient,
)
from PySide6.QtWidgets import QMenu, QWidget

from clarity_v.presence.colors import GlowColors
from clarity_v.state import State, StateManager


class StartStopButton(QWidget):
    """Floating draggable button that toggles dictation on click."""

    _state_changed = Signal(object)

    def __init__(
        self,
        state_manager: StateManager,
        on_toggle: Callable[[], str],
        colors: GlowColors | None = None,
        size: int = 56,
        brightness: float = 1.0,
        x: int | None = None,
        y: int | None = None,
        on_position_changed: Callable[[int, int], None] | None = None,
        on_toggle_button: Callable[[], None] | None = None,
        on_pause_resume: Callable[[], None] | None = None,
        on_settings: Callable[[], None] | None = None,
        on_about: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        on_toggle_glow_bar: Callable[[], None] | None = None,
        locked: bool = False,
        on_lock_changed: Callable[[bool], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._state_manager = state_manager
        self._on_toggle = on_toggle
        self._on_position_changed = on_position_changed
        self._on_toggle_button = on_toggle_button
        self._on_pause_resume = on_pause_resume
        self._on_settings = on_settings
        self._on_about = on_about
        self._on_quit = on_quit
        self._on_toggle_glow_bar = on_toggle_glow_bar
        self._paused = False
        self._colors = colors or GlowColors()
        self._size = size
        self._brightness = max(0.0, min(1.0, brightness))
        self._current_state = self._state_manager.state
        self._drag_offset: QPoint | None = None
        self._drag_start_pos: QPoint | None = None
        self._dragged = False
        self._locked = locked
        self._on_lock_changed = on_lock_changed

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self._size, self._size)

        # Default position: bottom-right corner with 24 px margins.
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geom = screen.geometry()
            default_x = geom.x() + geom.width() - self._size - 24
            default_y = geom.y() + geom.height() - self._size - 24
        else:
            default_x, default_y = 100, 100
        self.move(x if x is not None else default_x, y if y is not None else default_y)

        self._state_changed.connect(self._on_state_changed_qt)
        self._subscriber = self._on_state_event
        self._state_manager.subscribe(self._subscriber)

        self._reassert_timer = QTimer(self)
        self._reassert_timer.setInterval(200)
        self._reassert_timer.timeout.connect(self._reassert_topmost)
        self._reassert_timer.start()

    # ─── State pipeline ───────────────────────────────────────────────

    def _on_state_event(self, state, info):
        self._state_changed.emit(state)

    def _on_state_changed_qt(self, state):
        self._current_state = state
        self.update()

    # ─── Painting ─────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get size details
        pad = 6  # padding to accommodate drop shadow and bevel stroke width without clipping
        w = self._size - 2 * pad
        h = self._size - 2 * pad
        x = pad
        y = pad

        logo_w = w
        logo_h = h
        logo_y = y
        logo_x = x

        # Create the exact outer "C" crystal path with aligned coordinates
        c_path = QPainterPath()
        c_path.moveTo(logo_x + logo_w * 0.15, logo_y + logo_h * 0.05)
        c_path.lineTo(logo_x + logo_w * 0.85, logo_y + logo_h * 0.05)
        c_path.lineTo(logo_x + logo_w * 0.99, logo_y + logo_h * 0.25)
        # Top edge of horizontal channel
        c_path.lineTo(logo_x + logo_w * 0.76, logo_y + logo_h * 0.25)
        # Inner pocket ceiling (LT)
        c_path.lineTo(logo_x + logo_w * 0.24, logo_y + logo_h * 0.25)
        # Inner pocket left slant to bottom (B)
        c_path.lineTo(logo_x + logo_w * 0.50, logo_y + logo_h * 0.77)
        # Inner pocket right slant to channel bottom junction (R_MID)
        c_path.lineTo(logo_x + logo_w * 0.725, logo_y + logo_h * 0.32)
        # Bottom edge of horizontal channel
        c_path.lineTo(logo_x + logo_w * 0.96, logo_y + logo_h * 0.32)
        # Bottom-right outer slant to bottom tip
        c_path.lineTo(logo_x + logo_w * 0.50, logo_y + logo_h * 0.98)
        # Bottom-left outer slant to leftmost tip
        c_path.lineTo(logo_x + logo_w * 0.01, logo_y + logo_h * 0.25)
        c_path.closeSubpath()

        # 1. Draw a soft, blurred-looking drop shadow behind the crystal
        painter.save()
        painter.translate(0, 3)  # offset downward
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.setPen(QPen(QColor(0, 0, 0, 40), 3))
        painter.drawPath(c_path)
        painter.restore()

        # 2. Fill the "C" with purple crystal gradient
        grad = QLinearGradient(logo_x + logo_w / 2, logo_y, logo_x + logo_w / 2, logo_y + logo_h)
        grad.setColorAt(0.0, QColor(168, 85, 247, 245))  # #a855f7 vibrant purple/violet
        grad.setColorAt(1.0, QColor(76, 29, 149, 255))   # #4c1d95 deep rich purple
        painter.setBrush(grad)

        # 3. Draw crystal border (simulates bevel outline lit from top-down)
        c_pen_grad = QLinearGradient(logo_x + logo_w / 2, logo_y, logo_x + logo_w / 2, logo_y + logo_h)
        c_pen_grad.setColorAt(0.0, QColor(240, 220, 255, 255))  # very bright highlight at top
        c_pen_grad.setColorAt(0.3, QColor(216, 180, 254, 255))  # light lavender bevel
        c_pen_grad.setColorAt(1.0, QColor(110, 68, 180, 255))    # darker violet shadow border
        painter.setPen(QPen(c_pen_grad, 2))
        painter.drawPath(c_path)

        # Retrieve active state color
        r, g, b, _ = self._colors.for_state(self._current_state)
        
        # 4. Fill the inner "V" with 3D gradient matching active state
        v_grad = QLinearGradient(logo_x + logo_w / 2, logo_y + logo_h * 0.25, logo_x + logo_w / 2, logo_y + logo_h * 0.77)
        v_grad.setColorAt(0.0, QColor(r, g, b, 255))
        v_grad.setColorAt(1.0, QColor(max(0, r - 60), max(0, g - 60), max(0, b - 60), 255))
        painter.setBrush(v_grad)

        # Create dynamic "V" path matching pocket boundaries exactly (touches LT, B, RT)
        v_path = QPainterPath()
        v_path.moveTo(logo_x + logo_w * 0.24, logo_y + logo_h * 0.25)  # Touches LT
        v_path.lineTo(logo_x + logo_w * 0.50, logo_y + logo_h * 0.77)  # Touches B
        v_path.lineTo(logo_x + logo_w * 0.76, logo_y + logo_h * 0.25)  # Touches RT
        # Inner cutout of the hollow V
        v_path.lineTo(logo_x + logo_w * 0.64, logo_y + logo_h * 0.25)
        v_path.lineTo(logo_x + logo_w * 0.50, logo_y + logo_h * 0.53)
        v_path.lineTo(logo_x + logo_w * 0.36, logo_y + logo_h * 0.25)
        v_path.closeSubpath()

        # Stroke the "V" with a gradient (bevel highlight lit from top-down)
        v_pen_grad = QLinearGradient(logo_x + logo_w / 2, logo_y + logo_h * 0.25, logo_x + logo_w / 2, logo_y + logo_h * 0.77)
        v_pen_grad.setColorAt(0.0, QColor(min(255, r + 60), min(255, g + 60), min(255, b + 60), 255))  # bright top edge
        v_pen_grad.setColorAt(1.0, QColor(max(0, r - 20), max(0, g - 20), max(0, b - 20), 255))        # darker bottom tip
        painter.setPen(QPen(v_pen_grad, 1.5))
        painter.drawPath(v_path)

    # ─── Mouse handling ───────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Capture position relative to widget for drag tracking.
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._drag_start_pos = event.globalPosition().toPoint()
            self._dragged = False
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self._locked:
            return
        if event.buttons() & Qt.LeftButton and self._drag_offset is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            if not self._dragged and self._drag_start_pos is not None:
                if (event.globalPosition().toPoint() - self._drag_start_pos).manhattanLength() > 3:
                    self._dragged = True

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._dragged:
                # Persist the new position via the callback.
                if self._on_position_changed is not None:
                    p = self.pos()
                    self._on_position_changed(p.x(), p.y())
            else:
                # Pure click without drag → toggle dictation.
                try:
                    self._on_toggle()
                except Exception as e:
                    print(f"[StartStopButton] toggle callback raised: {e}")
            self._drag_offset = None
            self._dragged = False

    # ─── Context menu ─────────────────────────────────────────────────

    def _show_context_menu(self, global_pos):
        """Full app control surface — the Person reaches every action from
        the ball alone. Mirrors the tray menu (which Windows 11 often
        buries in overflow) plus the ball-specific Hide / Snap actions.
        """
        menu = QMenu()
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowStaysOnTopHint)

        # Engine control.
        if self._on_pause_resume is not None:
            pause_label = "Resume" if self._paused else "Pause"
            pause_action = QAction(pause_label, self)
            pause_action.triggered.connect(self._handle_pause_resume)
            menu.addAction(pause_action)

        # App control.
        if self._on_settings is not None:
            settings_action = QAction("Settings…", self)
            settings_action.triggered.connect(self._on_settings)
            menu.addAction(settings_action)

        if self._on_about is not None:
            about_action = QAction("About Clarity.V", self)
            about_action.triggered.connect(self._on_about)
            menu.addAction(about_action)

        if (
            self._on_pause_resume is not None
            or self._on_settings is not None
            or self._on_about is not None
        ):
            menu.addSeparator()

        # Ball-specific actions.
        toggle_bar_action = QAction("Toggle Glow Bar", self)
        toggle_bar_action.triggered.connect(
            lambda: self._on_toggle_glow_bar() if hasattr(self, '_on_toggle_glow_bar') and self._on_toggle_glow_bar else None
        )
        menu.addAction(toggle_bar_action)

        toggle_button_action = QAction("Toggle Float Button", self)
        toggle_button_action.triggered.connect(self._handle_hide)
        menu.addAction(toggle_button_action)

        menu.addSeparator()

        lock_action = QAction("Lock Position", self)
        lock_action.setCheckable(True)
        lock_action.setChecked(self._locked)
        lock_action.triggered.connect(self._toggle_lock)
        menu.addAction(lock_action)

        snap_menu = menu.addMenu("Snap to…")
        snap_menu.setEnabled(not self._locked)
        for label, corner in [
            ("Top-left", "top-left"),
            ("Top-right", "top-right"),
            ("Bottom-left", "bottom-left"),
            ("Bottom-right", "bottom-right"),
        ]:
            act = QAction(label, self)
            act.triggered.connect(lambda _, c=corner: self._snap_to(c))
            snap_menu.addAction(act)

        # Quit always lives at the bottom, after a separator, so it's
        # never the first item the Person reaches by accident.
        if self._on_quit is not None:
            menu.addSeparator()
            quit_action = QAction("Quit Clarity.V", self)
            quit_action.triggered.connect(self._on_quit)
            menu.addAction(quit_action)

        menu.exec(global_pos)

    def _handle_pause_resume(self) -> None:
        self._paused = not self._paused
        if self._on_pause_resume is not None:
            self._on_pause_resume()

    def _handle_hide(self):
        self.hide()
        if self._on_toggle_button is not None:
            self._on_toggle_button()

    def _toggle_lock(self):
        self._locked = not self._locked
        if self._on_lock_changed is not None:
            self._on_lock_changed(self._locked)

    def _snap_to(self, corner: str):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.geometry()
        margin = 24
        if corner == "top-left":
            x, y = geom.x() + margin, geom.y() + margin
        elif corner == "top-right":
            x, y = (geom.x() + geom.width() - self._size - margin, geom.y() + margin)
        elif corner == "bottom-left":
            x, y = (geom.x() + margin, geom.y() + geom.height() - self._size - margin)
        else:  # bottom-right
            x, y = (
                geom.x() + geom.width() - self._size - margin,
                geom.y() + geom.height() - self._size - margin,
            )
        self.move(x, y)
        if self._on_position_changed is not None:
            self._on_position_changed(x, y)

    # ─── Topmost re-assertion ─────────────────────────────────────────

    def _reassert_topmost(self):
        with contextlib.suppress(Exception):
            self.raise_()

    # ─── Cleanup ──────────────────────────────────────────────────────

    def closeEvent(self, event):
        with contextlib.suppress(Exception):
            self._state_manager.unsubscribe(self._subscriber)
        self._reassert_timer.stop()
        super().closeEvent(event)
