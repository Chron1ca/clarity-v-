import json
from pathlib import Path
from PySide6.QtCore import QObject, Slot, Signal

class SettingsBridge(QObject):
    settings_saved = Signal(object)
    mic_level_changed = Signal(float)

    def __init__(self, settings):
        super().__init__()
        self._s = settings
        self._dicts_dir = Path(__file__).resolve().parent.parent.parent.parent / "dictionaries"

    @Slot(result=str)
    def get_settings(self):
        import dataclasses
        return json.dumps(dataclasses.asdict(self._s))

    @Slot(str)
    def save_settings(self, json_str):
        import json
        from clarity_v.settings.model import WakeWordEntry
        data = json.loads(json_str)
        for k, v in data.items():
            if hasattr(self._s, k):
                if k == "wake_words" and isinstance(v, list):
                    v = [WakeWordEntry(**w) if isinstance(w, dict) else w for w in v]
                setattr(self._s, k, v)
        self._s.save()
        self.settings_saved.emit(self._s)

    @Slot(result=str)
    def fetch_audio_devices(self):
        import sounddevice as sd
        import json
        devices = []
        try:
            for i, info in enumerate(sd.query_devices()):
                if info["max_input_channels"] > 0:
                    devices.append({"index": i, "name": info.get("name", f"Device {i}")})
        except Exception:
            pass
        return json.dumps(devices)

    @Slot(result=str)
    def get_available_dictionaries(self):
        import json
        if not self._dicts_dir.exists():
            return "[]"
        files = [f.stem for f in self._dicts_dir.glob("*.json")]
        return json.dumps(files)

    @Slot(str, result=str)
    def load_dictionary(self, name):
        path = self._dicts_dir / f"{name}.json"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return "{}"

    @Slot(str, str)
    def save_dictionary(self, name, json_str):
        path = self._dicts_dir / f"{name}.json"
        path.write_text(json_str, encoding="utf-8")

    @Slot(result=str)
    def fetch_dictation_log(self):
        import json
        from clarity_v.dictation_log import DictationLog
        log = DictationLog()
        files = log.list_files()
        entries = []
        limit = 100
        for path in reversed(files):
            if len(entries) >= limit:
                break
            try:
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()
                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        entries.append(entry)
                        if len(entries) >= limit:
                            break
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                print(f"[Bridge] Failed to read log file {path}: {e}")
        return json.dumps(entries)

    @Slot(str)
    def copy_to_clipboard(self, text):
        import pyperclip
        try:
            pyperclip.copy(text)
            print(f"[Bridge] Copied text to clipboard: {text[:30]}...")
        except Exception as e:
            print(f"[Bridge] Clipboard copy failed: {e}")

    @Slot()
    def open_dictation_log_directory(self):
        import os
        from clarity_v.dictation_log import DEFAULT_LOG_DIR
        try:
            if not DEFAULT_LOG_DIR.exists():
                DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
            # Use os.startfile on Windows
            os.startfile(str(DEFAULT_LOG_DIR))
            print(f"[Bridge] Opened dictation logs directory: {DEFAULT_LOG_DIR}")
        except Exception as e:
            print(f"[Bridge] Failed to open dictation log directory: {e}")

    def _get_paths(self):
        import sys
        import shutil
        from pathlib import Path

        frozen = getattr(sys, "frozen", False)
        repo_root = None

        if not frozen:
            # D:\clarity\Clarity-repo\src\clarity_v\settings\bridge.py -> 4 parents to Clarity-repo
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
        else:
            exe_path = Path(sys.executable).resolve()
            # Candidate 1: dist/clarity-v/clarity-v.exe
            if (exe_path.parent.parent.parent / "tools" / "training" / "wizard.py").exists():
                repo_root = exe_path.parent.parent.parent
            # Candidate 2: dist/clarity-v.exe
            elif (exe_path.parent.parent / "tools" / "training" / "wizard.py").exists():
                repo_root = exe_path.parent.parent
            # Candidate 3: CWD
            elif (Path.cwd() / "tools" / "training" / "wizard.py").exists():
                repo_root = Path.cwd()
            else:
                repo_root = Path(__file__).resolve().parent.parent.parent.parent

        wizard_path = repo_root / "tools" / "training" / "wizard.py"

        py_exe = None
        if not frozen:
            py = sys.executable
            if py.lower().endswith("pythonw.exe"):
                py_exe = py[:-9] + "python.exe"
            elif py.lower().endswith("pythonw"):
                py_exe = py[:-7] + "python"
            else:
                py_exe = py
        else:
            # Frozen: look for developer environment's virtualenv python
            venv_py = repo_root / ".venv" / "Scripts" / "python.exe"
            if venv_py.exists():
                py_exe = str(venv_py)
            else:
                sys_py = shutil.which("python")
                py_exe = sys_py if sys_py else "python"

        return repo_root, wizard_path, py_exe

    @Slot()
    def start_wake_word_wizard(self):
        import subprocess
        
        _, wizard_path, py_exe = self._get_paths()
        # Wrap the commands in outer double quotes for cmd.exe /k to prevent quote stripping
        cmd = f'cmd.exe /c start cmd.exe /k ""{py_exe}" "{wizard_path}""'
        try:
            subprocess.Popen(cmd)
            print("[Bridge] Launched wake word training wizard in new console window.")
        except Exception as e:
            print(f"[Bridge] Failed to launch wake word wizard: {e}")

    @Slot(str, str)
    def start_wake_word_wizard_for(self, phrase, model_name):
        import subprocess
        
        _, wizard_path, py_exe = self._get_paths()
        # Sanitize phrase and model name to avoid quote injection issues
        phrase_clean = phrase.replace('"', '')
        model_name_clean = model_name.replace('"', '')
        # Wrap the commands in outer double quotes for cmd.exe /k to prevent quote stripping
        cmd = f'cmd.exe /c start cmd.exe /k ""{py_exe}" "{wizard_path}" --phrase "{phrase_clean}" --model-name "{model_name_clean}""'
        try:
            subprocess.Popen(cmd)
            print(f"[Bridge] Launched wake word training wizard for '{phrase_clean}' ({model_name_clean}).")
        except Exception as e:
            print(f"[Bridge] Failed to launch wake word wizard for '{phrase}': {e}")

    @Slot(str, str)
    def personalize_wake_word(self, phrase, model_name):
        """Launch calibrate.py to retune the trigger threshold to this
        user's voice for an existing wake word. ~60 seconds, no downloads,
        runs in the runtime venv (calibrate.py only needs sounddevice
        and openwakeword, both already runtime deps)."""
        import subprocess

        repo_root, _, py_exe = self._get_paths()
        calibrate_path = repo_root / "tools" / "training" / "calibrate.py"
        model_path = repo_root / "models" / "wake_words" / f"{model_name}.onnx"

        phrase_clean = phrase.replace('"', '')
        model_name_clean = model_name.replace('"', '')

        cmd = (
            f'cmd.exe /c start cmd.exe /k '
            f'""{py_exe}" "{calibrate_path}" '
            f'--phrase "{phrase_clean}" --model "{model_path}""'
        )
        try:
            subprocess.Popen(cmd)
            print(
                f"[Bridge] Launched wake word personalize for "
                f"'{phrase_clean}' ({model_name_clean})."
            )
        except Exception as e:
            print(
                f"[Bridge] Failed to launch wake word personalize "
                f"for '{phrase}': {e}"
            )

    @Slot(int, result=str)
    def fetch_engine_log(self, after_index):
        """Return engine log lines after the given index as JSON."""
        from clarity_v.log_capture import get_lines_since
        return json.dumps(get_lines_since(after_index))

