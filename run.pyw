"""
Clarity.V entry point — windowed launch, no console.

Run with: double-click run.pyw on Windows, or:
    pythonw run.pyw

stdout / stderr are redirected to ~/.clarity_v/clarity_v.log with
immediate flushing. No CMD box ever appears. If something goes wrong
during boot, the log file is where the traceback lands.
"""

import os
import sys
from pathlib import Path

# Configure Windows Taskbar AppUserModelID
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("chron1ca.clarity_v.1.0")
    except Exception:
        pass


def _setup_logging() -> Path:
    """Redirect stdout + stderr to ~/.clarity_v/clarity_v.log.

    Uses a small wrapper that flushes after every write so the log is
    always current — no buffered surprise after a crash.
    """
    log_dir = Path.home() / ".clarity_v"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "clarity_v.log"

    fh = open(log_path, "a", encoding="utf-8", buffering=1)  # line-buffered

    class _Tee:
        def __init__(self, f):
            self._f = f

        def write(self, s):
            self._f.write(s)
            self._f.flush()

        def flush(self):
            self._f.flush()

        def isatty(self):
            return False

    tee = _Tee(fh)
    sys.stdout = tee
    sys.stderr = tee
    return log_path


# Redirect BEFORE any clarity_v import so all engine print() calls
# land in the log.
_log_path = _setup_logging()

# Make src/ importable when running from repo root.
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Mark session start (run.pyw may append across many launches).
print("=" * 60)
print(f"Clarity.V starting (pid={os.getpid()})")
print(f"Log file: {_log_path}")
print("=" * 60)

from clarity_v.app import main  # noqa: E402

if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001
        import traceback

        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
