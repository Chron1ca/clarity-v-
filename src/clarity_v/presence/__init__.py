"""
Presence — the visual layer.

The glow bar at the top of the screen and the system tray icon. Both
subscribe to a StateManager and update their appearance whenever state
changes.

Public surface:
    from clarity_v.presence import PresenceApp
    app = PresenceApp(state_manager)
    app.start()  # runs Qt event loop on the main thread
"""

from clarity_v.presence.app import PresenceApp

__all__ = ["PresenceApp"]
