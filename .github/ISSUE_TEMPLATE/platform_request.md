---
name: Platform request
about: You want Clarity.V to work on an OS or environment not yet supported
title: 'Platform: '
labels: platform
assignees: ''
---

## Platform

OS / distro / environment you want Clarity.V to run on:

## What works for that platform's competitors

Brief note on what other voice tools (Dragon, Whisper-only frontends, etc.) do for this platform that Clarity.V should match.

## Have you tried implementing it?

See [CONTRIBUTING.md § Add a platform](../CONTRIBUTING.md#add-a-platform). The platform adapter interface is `src/clarity_v/platform/_base.py` — one file behind a narrow API. If you've started, link your fork.

## Specific OS-level questions

- Hotkey listener API:
- Synthetic keystroke API:
- Always-on-top window APIs:
- Audio capture (does sounddevice/PortAudio work?):
- Clipboard / paste mechanism:
- Notarization / code-signing requirements:
