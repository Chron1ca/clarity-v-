"""
Platform adapter layer.

Every OS-specific detail (hotkey listening, synthetic key events, paste
mechanism, audio cue playback, system tray) lives behind the interface in
`_base.py`. Each supported OS implements that interface in its own file.

To add a new platform: implement `PlatformAdapter` in `<yourname>.py`,
register it in `get_adapter()` below, ship a PR. No other module in
Clarity.V should need to change.

Current state:
- windows.py     — v1.0 — primary support
- linux_x11.py   — v1.1 planned
- macos.py       — v1.2 planned
- linux_wayland.py — v1.3 planned (Wayland's security model is restrictive;
                     needs ydotool / portal-based key injection)
"""

import sys

from clarity_v.platform._base import PlatformAdapter


def get_adapter() -> PlatformAdapter:
    """Return the adapter for the current OS.

    Raises RuntimeError if no adapter exists for this platform yet.
    """
    if sys.platform == "win32":
        from clarity_v.platform.windows import WindowsAdapter

        return WindowsAdapter()
    if sys.platform.startswith("linux"):
        # X11 detection: $DISPLAY set, no $WAYLAND_DISPLAY.
        import os

        if os.environ.get("WAYLAND_DISPLAY"):
            raise RuntimeError(
                "Wayland support is planned for v1.3. "
                "For now, run on an X11 session, or contribute a "
                "linux_wayland.py adapter — see "
                "src/clarity_v/platform/_base.py for the interface."
            )
        from clarity_v.platform.linux_x11 import LinuxX11Adapter

        return LinuxX11Adapter()
    if sys.platform == "darwin":
        from clarity_v.platform.macos import MacOSAdapter

        return MacOSAdapter()
    raise RuntimeError(
        f"No Clarity.V platform adapter for sys.platform={sys.platform!r}. "
        f"Implement one — see src/clarity_v/platform/_base.py."
    )


__all__ = ["PlatformAdapter", "get_adapter"]
