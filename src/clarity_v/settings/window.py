import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

from clarity_v.settings.model import Settings
from clarity_v.settings.bridge import SettingsBridge


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, on_apply=None, parent=None):
        super().__init__(parent)
        self.s = settings
        self.on_apply = on_apply

        self.setWindowTitle("Clarity.V Settings")
        self.resize(900, 700)
        self.setMinimumSize(900, 650)
        
        self.setAttribute(Qt.WA_DeleteOnClose)

        # Load and set window icon
        icon_path = Path(__file__).resolve().parent.parent.parent.parent / "cv_logo.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.view = QWebEngineView()
        layout.addWidget(self.view)
        
        self.channel = QWebChannel()
        self.bridge = SettingsBridge(self.s)
        if self.on_apply:
            self.bridge.settings_saved.connect(self.on_apply)
            
        self.channel.registerObject("backend", self.bridge)
        self.view.page().setWebChannel(self.channel)
        
        # Force correct DPI rendering on Windows by nudging geometry
        # after the page finishes loading.
        self.view.loadFinished.connect(self._on_load_finished)
        
        html_path = Path(__file__).resolve().parent / "ui_web" / "settings.html"
        self.view.setUrl(QUrl.fromLocalFile(str(html_path)))

    def _on_load_finished(self, ok):
        """Nudge the dialog geometry so Qt recalculates DPI scaling.
        
        QWebEngineView on Windows high-DPI can initially render at 1x
        until a resize event forces the compositor to recalculate. This
        adds 1px then removes it, invisible to the user, fixes the blur.
        """
        if ok:
            r = self.geometry()
            self.setGeometry(r.x(), r.y(), r.width() + 1, r.height())
            QTimer.singleShot(50, lambda: self.setGeometry(r))

    def closeEvent(self, event):
        """Tear down WebEngine resources immediately to terminate Chromium processes."""
        if hasattr(self, "view") and self.view:
            page = self.view.page()
            if page:
                page.setWebChannel(None)
                page.deleteLater()
            self.view.setParent(None)
            self.view.deleteLater()
        super().closeEvent(event)


def open_settings_window(settings=None, on_apply=None):
    import sys
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("chron1ca.clarity_v.1.0")
        except Exception:
            pass

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    # Set application icon if not already set
    icon_path = Path(__file__).resolve().parent.parent.parent.parent / "cv_logo.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    if settings is None:
        settings = Settings.load()
        
    dlg = SettingsDialog(settings, on_apply)
    
    # Store reference on the application to prevent garbage collection
    if not hasattr(app, "_settings_dialogs"):
        app._settings_dialogs = []
    app._settings_dialogs.append(dlg)
    
    # Clean up the reference when the dialog is closed/destroyed
    dlg.destroyed.connect(lambda: app._settings_dialogs.remove(dlg) if dlg in app._settings_dialogs else None)
    
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg


from clarity_v.settings.model import WakeWordEntry

def _format_wake_word_entry(w: WakeWordEntry) -> str:
    parts = [f"name={w.name}"]
    if w.model_path:
        parts.append(f"model_path={w.model_path}")
    parts.append(f"threshold={w.threshold}")
    parts.append(f"role={w.role}")
    return " ".join(parts)

def _parse_wake_word_entry(line: str) -> WakeWordEntry | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    kv: dict[str, str] = {}
    for tok in line.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            kv[k] = v
    name = kv.get("name", "")
    if not name:
        return None
    try:
        threshold = float(kv.get("threshold", "0.5"))
    except ValueError:
        threshold = 0.5
    return WakeWordEntry(
        name=name,
        model_path=kv.get("model_path"),
        threshold=threshold,
        role=kv.get("role", "start"),
    )
