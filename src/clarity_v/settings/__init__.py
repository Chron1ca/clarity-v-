"""
Settings — persisted user preferences + the Qt UI to edit them.

Public surface:
    from clarity_v.settings import Settings, open_settings_window

    s = Settings.load()          # from ~/.clarity_v/settings.json
    print(s.silence_threshold)
    s.silence_threshold = 0.01
    s.save()

    # Or via UI:
    open_settings_window(state_manager, on_apply=lambda s: ...)
"""

from clarity_v.settings.model import Settings, default_path
from clarity_v.settings.window import open_settings_window

__all__ = ["Settings", "default_path", "open_settings_window"]
