# Packaging Clarity.V

This directory holds platform-specific build configuration.

## Windows (PyInstaller)

```bash
# In the runtime venv:
pip install pyinstaller
pyinstaller packaging/clarity_v.spec
```

Output: `dist/clarity-v/clarity-v.exe` plus supporting DLLs and data. To distribute, zip the `dist/clarity-v/` directory or wrap it with [Inno Setup](https://jrsoftware.org/isinfo.php) for a one-file installer.

### What's bundled

- `clarity-v.exe` and Python runtime
- Default + Python dictionaries
- `models/wake_words/` directory (custom ONNX files added by user)
- All documentation (README, LICENSE, ARCHITECTURE, PRIVACY, CONTRIBUTING, TRAINING)

### What's NOT bundled

- **Whisper model** — downloaded by Whisper at first run to `~/.cache/`. Including it would push the installer to ~2 GB.
- **Training pipeline** — `edge-tts`, `librosa`, `torch_audiomentations` are excluded. Training is a separate venv (see [TRAINING.md](../TRAINING.md)).

## macOS — planned (v1.2)

`packaging/clarity_macos.spec` will mirror the Windows spec, plus:

- `.app` bundle structure
- Code signing via the Apple Developer ID
- Notarization step (`xcrun notarytool`)
- DMG generation

## Linux — planned (v1.1 / v1.3)

X11 build is straightforward via PyInstaller; same spec as Windows with the platform adapter swap. Wayland build needs portal-based hotkey/key-synthesis (v1.3).

Packaging formats considered:

- **AppImage** — single-file, works on most distros
- **Flatpak** — needs sandbox permissions for global hotkeys + clipboard
- **deb/rpm** — distro-specific, more work
