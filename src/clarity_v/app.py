"""
Clarity.V application entry point.

Wires the engine + presence + settings into a runnable program:

    DictationEngine    ←─── shared StateManager ───→    PresenceApp
         (audio                                          (Qt glow bar
          thread)                                         + tray icon)

The dictation engine runs the audio capture / wake / transcribe loop
on its own threads. The PresenceApp owns the Qt event loop on the main
thread. State changes in the engine propagate to the presence layer
through the shared StateManager.

To launch:
    pythonw run.pyw  (Windows — no console)
    python  run.pyw  (cross-platform; will show a console on Windows)
"""

from __future__ import annotations

import contextlib
import signal
import sys

from PySide6.QtWidgets import QMessageBox

from clarity_v import __version__
from clarity_v.dictation import DictationConfig, DictationEngine
from clarity_v.dictation_log import DictationLog
from clarity_v.platform import get_adapter
from clarity_v.presence import PresenceApp
from clarity_v.presence.colors import GlowColors
from clarity_v.settings import Settings, open_settings_window
from clarity_v.sounds import SoundCues
from clarity_v.state import StateManager


def _make_engine_config(s: Settings) -> DictationConfig:
    """Translate persisted Settings into the engine's runtime config."""
    wake_config = {
        "models": [
            {
                "name": w.name,
                **({"model_path": w.model_path} if w.model_path else {}),
                "threshold": w.threshold,
                "role": w.role,
            }
            for w in s.wake_words
        ],
        "cooldown_seconds": s.wake_cooldown_seconds,
    }
    return DictationConfig(
        whisper_model=s.whisper_model_size,
        language_lock=s.language_lock,
        whisper_initial_prompt=s.whisper_initial_prompt,
        wake_config=wake_config,
        audio_device=s.audio_device_index,
        silence_rms_threshold=s.silence_rms_threshold,
        silence_seconds_to_stop=s.silence_seconds_to_stop,
        min_recording_seconds=s.min_recording_seconds,
        commit_window_seconds=s.commit_window_seconds,
        profiles_enabled=s.profiles_enabled,
        in_dictation_commands_enabled=s.in_dictation_commands_enabled,
        wake_words_enabled=s.wake_words_enabled,
        vocabulary_blacklist=s.vocabulary_blacklist,
    )


def _to_rgba(c: list[int]) -> tuple[int, int, int, int]:
    if len(c) >= 4:
        return (c[0], c[1], c[2], c[3])
    return (255, 255, 255, 0)  # fallback

def _make_colors(s: Settings) -> GlowColors:
    """Translate persisted Settings colors into a GlowColors instance."""
    return GlowColors(
        idle=_to_rgba(s.color_idle),
        recording=_to_rgba(s.color_recording),
        processing=_to_rgba(s.color_processing),
        commit_waiting=_to_rgba(s.color_commit_waiting),
        error=_to_rgba(s.color_error),
    )


def main(argv: list | None = None) -> int:
    import sys
    if argv is None:
        argv = sys.argv

    # Install stdout capture FIRST — before any print() calls — so the
    # Engine Console tab in Settings can show all backend output live.
    from clarity_v.log_capture import install as install_log_capture
    install_log_capture()

    # Ensure QApplication is initialized early so we can use Qt classes (QLocalSocket / QLocalServer)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if not app:
        app = QApplication(argv)

    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("chron1ca.clarity_v.1.0")
        except Exception:
            pass

    # Single-instance check via QLocalServer / QLocalSocket
    server = None
    if "--no-ipc" not in argv:
        from PySide6.QtNetwork import QLocalSocket, QLocalServer
        ipc_name = "ClarityV_IPC"
        
        # Try connecting to existing server
        socket = QLocalSocket()
        socket.connectToServer(ipc_name)
        if socket.waitForConnected(500):
            print("[App] Another instance is already running. Requesting it to show settings...")
            socket.write(b"show_settings")
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            return 0
            
        # No other instance running, start our IPC server
        server = QLocalServer()
        QLocalServer.removeServer(ipc_name)
        if not server.listen(ipc_name):
            print(f"[App] Warning: Failed to start IPC local server: {server.errorString()}")

    print("Clarity.V — local voice dictation")
    print("=" * 60)

    settings = Settings.load()
    print(f"Settings: {settings.__class__.__name__} loaded.")

    state_manager = StateManager()

    # Dictation log — opt-in via settings, rotates at the configured KB.
    dictation_log: DictationLog | None = None
    if settings.dictation_log_enabled:
        dictation_log = DictationLog(
            max_bytes=settings.dictation_log_max_kb * 1024,
        )
        print(f"Dictation log enabled: {dictation_log.current_path}")

    # Platform adapter — shared between engine and sound cues.
    platform = get_adapter()

    # Cue tones — opt-out via settings. Three of them: activate,
    # deactivate, and paste. Paste fires when text lands at the cursor
    # and marks the start of the commit window for "send" / "enter".
    sound_cues = SoundCues(
        platform=platform,
        enabled=settings.sound_enabled,
        activate_path=Path(settings.sound_activate_path) if settings.sound_activate_path else None,
        deactivate_path=Path(settings.sound_deactivate_path) if settings.sound_deactivate_path else None,
        paste_path=Path(settings.sound_paste_path) if settings.sound_paste_path else None,
        volume=settings.sound_volume,
    )

    # Engine. Construction is heavy (Whisper model load); do it once.
    print("Loading engine (Whisper + wake + dictionary + platform)...")
    engine_cfg = _make_engine_config(settings)
    engine = DictationEngine(
        config=engine_cfg,
        state_manager=state_manager,
        platform=platform,
        dictation_log=dictation_log,
        sound_cues=sound_cues,
    )

    def _apply_keybinds():
        engine.platform.unregister_all_hotkeys()
        
        # Toggle keybind
        if settings.keybind_toggle:
            try:
                engine.platform.register_hotkey(
                    settings.keybind_toggle,
                    on_press=engine.toggle_recording,
                    suppress=True,
                )
                print(f"Toggle keybind: {settings.keybind_toggle}")
            except Exception as e:
                print(f"[App] Failed to register toggle keybind: {e}")

        # Push-to-Talk keybind
        if settings.keybind_ptt:
            try:
                engine.platform.register_hotkey(
                    settings.keybind_ptt,
                    on_press=engine.ptt_press,
                    on_release=engine.ptt_release,
                    suppress=True,
                )
                print(f"PTT keybind: {settings.keybind_ptt}")
            except Exception as e:
                print(f"[App] Failed to register PTT keybind: {e}")

        # Paste-last-dictation keybind
        if settings.keybind_paste_last_dictation:
            try:
                engine.platform.register_hotkey(
                    settings.keybind_paste_last_dictation,
                    on_press=engine.paste_last_dictation,
                    suppress=True,
                )
                print(f"Paste-last keybind: {settings.keybind_paste_last_dictation}")
            except Exception as e:
                print(f"[App] Failed to register paste-last keybind: {e}")

        # Cancel-dictation keybind
        if settings.keybind_cancel:
            try:
                engine.platform.register_hotkey(
                    settings.keybind_cancel,
                    on_press=engine.cancel_dictation,
                    suppress=True,
                )
                print(f"Cancel keybind: {settings.keybind_cancel}")
            except Exception as e:
                print(f"[App] Failed to register cancel keybind: {e}")

        # Dictionary keybinds
        for dict_name, kb in getattr(settings, 'dictionary_keybinds', {}).items():
            if kb:
                try:
                    def make_switcher(name):
                        def switch():
                            engine.dictionary.load(name)
                            settings.active_dictionary = name
                            settings.save()
                            print(f"[App] Switched dictionary to {name} via hotkey")
                            if engine.sound_cues:
                                engine.sound_cues.play_activate()
                        return switch

                    engine.platform.register_hotkey(
                        kb,
                        on_press=make_switcher(dict_name),
                        suppress=True,
                    )
                    print(f"Dictionary '{dict_name}' keybind: {kb}")
                except Exception as e:
                    print(f"[App] Failed to register dictionary keybind '{kb}': {e}")

    # Initial keybind setup
    _apply_keybinds()

    # Presence (glow bar + tray) — only if settings allow.
    presence: PresenceApp | None = None
    if settings.show_glow_bar or settings.show_tray_icon:
        colors = _make_colors(settings)

        # Tray callbacks bridge to engine + settings.
        paused = [False]
        settings_open = [False]

        def toggle_pause():
            paused[0] = not paused[0]
            if paused[0]:
                engine.stop()
                print("[App] Paused.")
            else:
                engine.start()
                print("[App] Resumed.")

        def open_settings():
            if settings_open[0]:
                from PySide6.QtWidgets import QApplication
                from clarity_v.settings.window import SettingsDialog
                for w in QApplication.topLevelWidgets():
                    if isinstance(w, SettingsDialog):
                        w.showNormal()
                        w.raise_()
                        w.activateWindow()
                        return
                
                active_modal = QApplication.activeModalWidget()
                if active_modal:
                    active_modal.showNormal()
                    active_modal.raise_()
                    active_modal.activateWindow()
                return
            settings_open[0] = True

            old_toggle = settings.keybind_toggle
            old_ptt = settings.keybind_ptt
            old_paste = settings.keybind_paste_last_dictation
            old_cancel = settings.keybind_cancel
            old_dict_kb = dict(getattr(settings, 'dictionary_keybinds', {}))

            def on_apply_live(new_settings):
                # 1. Hot-reload keybinds
                nonlocal old_toggle, old_ptt, old_paste, old_cancel, old_dict_kb
                new_dict_kb = getattr(new_settings, 'dictionary_keybinds', {})
                if (new_settings.keybind_toggle != old_toggle or 
                    new_settings.keybind_ptt != old_ptt or 
                    new_settings.keybind_paste_last_dictation != old_paste or 
                    new_settings.keybind_cancel != old_cancel or
                    new_dict_kb != old_dict_kb):
                    print("[App] Keybinds changed, hot-reloading...")
                    _apply_keybinds()
                    old_toggle = new_settings.keybind_toggle
                    old_ptt = new_settings.keybind_ptt
                    old_paste = new_settings.keybind_paste_last_dictation
                    old_cancel = new_settings.keybind_cancel
                    old_dict_kb = dict(new_dict_kb)
                
                # 2. Hot-reload presence UI
                if presence is not None:
                    print("[App] Visuals changed, hot-reloading presence UI...")
                    presence.reload_ui(new_settings)
                    
            def on_dialog_finished(result):
                settings_open[0] = False
                print(
                    "[App] Settings window closed. Restart Clarity.V to apply engine "
                    "changes (model, audio device)."
                )

            try:
                dlg = open_settings_window(settings, on_apply=on_apply_live)
                if dlg:
                    dlg.finished.connect(on_dialog_finished)
            except Exception as e:
                print(f"[App] Failed to open settings: {e}")
                settings_open[0] = False

        def show_about():
            QMessageBox.about(
                None,
                "About Clarity.V",
                (
                    f"<h3>Clarity.V <small>v{__version__}</small></h3>"
                    "<p>Local voice dictation. Free, open, fork-friendly.</p>"
                    "<p>By <a href='https://github.com/Chron1ca'>"
                    "Chron1ca (Gonçalo Mattos Parreira)</a>.</p>"
                    "<p>See <a href='https://github.com/Chron1ca/clarity-v'>"
                    "the repo</a> · "
                    "<a href='https://uplane.host'>U.Plane</a> "
                    "(the commercial sibling).</p>"
                    "<p><small>Settings are at "
                    "<code>~/.clarity_v/settings.json</code>; "
                    "log at <code>~/.clarity_v/clarity_v.log</code>.</small></p>"
                ),
            )

        # Floating start/stop button callbacks. Position changes are
        # persisted live so the button shows up where it was last left.
        def on_button_moved(x: int, y: int) -> None:
            settings.start_stop_button_x = x
            settings.start_stop_button_y = y
            try:
                settings.save()
            except Exception as e:
                print(f"[App] Failed to persist button position: {e}")

        def on_button_locked(locked: bool) -> None:
            settings.start_stop_button_locked = locked
            try:
                settings.save()
            except Exception as e:
                print(f"[App] Failed to persist button lock: {e}")

        def toggle_glow_bar() -> None:
            settings.show_glow_bar = not settings.show_glow_bar
            try:
                settings.save()
            except Exception as e:
                print(f"[App] Failed to persist glow bar toggle: {e}")
            if presence is not None:
                presence.reload_ui(settings)

        def toggle_button() -> None:
            settings.show_start_stop_button = not settings.show_start_stop_button
            try:
                settings.save()
            except Exception as e:
                print(f"[App] Failed to persist button toggle: {e}")
            if presence is not None:
                presence.reload_ui(settings)

        def copy_last_transcript() -> None:
            text = engine.last_buffer.get()
            if text:
                import pyperclip
                try:
                    pyperclip.copy(text)
                    print(f"[App] Copied last transcript to clipboard: {text[:30]}...")
                except Exception as e:
                    print(f"[App] Failed to copy last transcript: {e}")

        presence = PresenceApp(
            state_manager,
            colors=colors,
            show_bar=settings.show_glow_bar,
            show_tray=settings.show_tray_icon,
            bar_height=settings.glow_bar_height,
            bar_brightness=settings.glow_bar_brightness,
            bar_position=settings.glow_bar_position,
            bar_freeform_x=settings.glow_bar_x,
            bar_freeform_y=settings.glow_bar_y,
            show_start_stop_button=settings.show_start_stop_button,
            start_stop_button_locked=settings.start_stop_button_locked,
            start_stop_button_size=settings.start_stop_button_size,
            start_stop_button_x=settings.start_stop_button_x,
            start_stop_button_y=settings.start_stop_button_y,
            on_toggle_dictation=engine.toggle_recording,
            on_button_moved=on_button_moved,
            on_button_locked=on_button_locked,
            on_pause_resume=toggle_pause,
            on_settings=open_settings,
            on_about=show_about,
            on_toggle_glow_bar=toggle_glow_bar,
            on_toggle_button=toggle_button,
            on_copy_last_transcript=copy_last_transcript,
        )

        if server is not None:
            def handle_new_connection():
                sock = server.nextPendingConnection()
                if sock.waitForReadyRead(500):
                    msg = sock.readAll().data().decode("utf-8").strip()
                    if msg == "show_settings":
                        print("[App] Received show_settings request from another instance.")
                        from PySide6.QtCore import QTimer
                        QTimer.singleShot(0, open_settings)
                sock.disconnectFromServer()
            server.newConnection.connect(handle_new_connection)

        # Check if we should start with settings open
        if "--settings" in argv:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, open_settings)

    # Start the engine (audio thread spins up).
    engine.start()

    # Graceful shutdown on Ctrl+C.
    def _cleanup(*_):
        sys.exit(0)

    # SIGINT may not be available on all platforms / non-main threads.
    with contextlib.suppress(AttributeError, ValueError):
        signal.signal(signal.SIGINT, _cleanup)

    try:
        if presence is not None:
            # Blocks on Qt event loop. Cleanup happens via tray quit or signal.
            return presence.start()

        # Headless mode: just block on stdin.
        print("[App] Headless mode (no presence UI). Press Ctrl+C to quit.")
        try:
            while True:
                import time

                time.sleep(60)
        except KeyboardInterrupt:
            pass
        return 0
    finally:
        print("\n[App] Shutting down...")
        try:
            import threading
            import time
            def _watchdog():
                time.sleep(3.0)
                print("[App] Watchdog: Cleanup took too long. Force exiting process.")
                import os
                os._exit(0)
            threading.Thread(target=_watchdog, daemon=True, name="ShutdownWatchdog").start()
        except Exception as e:
            print(f"[App] Failed to start shutdown watchdog: {e}")

        try:
            engine.stop()
        except Exception as e:
            print(f"[App] Error stopping engine: {e}")
            
        try:
            engine.platform.unregister_all_hotkeys()
        except Exception as e:
            print(f"[App] Error unregistering hotkeys: {e}")
            
        try:
            if presence is not None:
                presence.quit()
        except Exception as e:
            print(f"[App] Error quitting presence: {e}")
            
        try:
            if server is not None:
                server.close()
        except Exception as e:
            print(f"[App] Error closing server: {e}")
            
        print("[App] Teardown complete. Force exiting process.")
        import os
        os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
