import sys
import shutil
from pathlib import Path
import site

# Find the qwebchannel.js file inside PySide6
site_packages = Path(site.getsitepackages()[0])
pyside_dir = site_packages / "PySide6"

qwebchannel_src = None
for p in pyside_dir.rglob("qwebchannel.js"):
    qwebchannel_src = p
    break

dest = Path("src/clarity_v/settings/ui_web/lib/qwebchannel.js")
if qwebchannel_src and qwebchannel_src.exists():
    shutil.copy(qwebchannel_src, dest)
    print("Copied qwebchannel.js")
else:
    print("qwebchannel.js not found in PySide6. Using remote fallback.")
