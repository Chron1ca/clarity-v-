# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Clarity.V v1.0 — Windows build.

Usage (from repo root, with the runtime venv active):
    pip install pyinstaller
    pyinstaller packaging/clarity_v.spec

Produces:
    dist/clarity-v/clarity-v.exe   (+ supporting files)
    build/                     (intermediate; can be deleted)

Notes:
- Bundles the Whisper model lazily — at runtime Whisper downloads to
  the user's ~/.cache directory on first use. Including it in the build
  would inflate the installer to ~2 GB.
- Bundles the default + python dictionaries.
- Bundles the wake_words directory (empty at first; custom ONNX files
  go here after training).
- Does NOT bundle pynput backend binaries — pynput resolves them at
  import time on the user's machine.
"""

import sys
from pathlib import Path

# Repo root
ROOT = Path(SPECPATH).parent

block_cipher = None

# Data files to bundle (relative paths in the bundle = first elem of tuple)
datas = [
    (str(ROOT / "dictionaries"), "dictionaries"),
    (str(ROOT / "models" / "wake_words"), "models/wake_words"),
    (str(ROOT / "README.md"), "."),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "ARCHITECTURE.md"), "."),
    (str(ROOT / "PRIVACY.md"), "."),
    (str(ROOT / "CONTRIBUTING.md"), "."),
    (str(ROOT / "TRAINING.md"), "."),
]

# Hidden imports — packages PyInstaller can't auto-detect from imports
hiddenimports = [
    "openwakeword",
    "openwakeword.model",
    "faster_whisper",
    "ctranslate2",
    "sounddevice",
    "pynput.keyboard",
    "pynput.mouse",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    # Whisper's tokenizer pulls these in lazily
    "tiktoken",
    "regex",
]

a = Analysis(
    [str(ROOT / "run.pyw")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Don't ship the training pipeline with the runtime build.
        # Training has different version constraints (see TRAINING.md).
        "torch_audiomentations",
        "librosa",
        "edge_tts",
        # Big test/dev deps we never need at runtime
        "pytest",
        "jupyter",
        "notebook",
        "matplotlib",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="clarity-v",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX can break Qt/PyTorch on some Windows configs.
    console=False,       # GUI app — no console window.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "cv_logo.ico"),           # Replace with icon path when one exists.
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="clarity-v",
)
