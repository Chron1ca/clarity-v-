from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication
import pytest

from clarity_v.state import State, StateManager
from clarity_v.presence.overlay import GlowBar
from clarity_v.presence.start_stop_button import StartStopButton
from clarity_v.presence.tray import ClarityTray
from clarity_v.presence.colors import GlowColors


@pytest.fixture(scope="module")
def q_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_visual_elements_initialize_with_current_state(q_app):
    # Set up a StateManager in RECORDING state
    state_manager = StateManager()
    state_manager.set_state(State.RECORDING)
    assert state_manager.state == State.RECORDING

    colors = GlowColors()

    # 1. GlowBar
    glow_bar = GlowBar(state_manager, colors=colors)
    # The expected alpha-adjusted color for State.RECORDING
    r, g, b, a = colors.for_state(State.RECORDING)
    expected_alpha = int(a * glow_bar._brightness)
    assert glow_bar._current_color.red() == r
    assert glow_bar._current_color.green() == g
    assert glow_bar._current_color.blue() == b
    assert glow_bar._current_color.alpha() == expected_alpha
    glow_bar.close()

    # 2. StartStopButton
    button = StartStopButton(state_manager, on_toggle=lambda: "toggled", colors=colors)
    assert button._current_state == State.RECORDING
    button.close()

    # 3. ClarityTray
    tray = ClarityTray(state_manager, colors=colors)
    assert tray.toolTip() == f"Clarity.V — {State.RECORDING.value}"
    tray.hide()
