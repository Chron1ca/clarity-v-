# Privacy

The short version: **your audio never leaves your computer.**

The long version, with code references so you can verify it yourself, follows.

---

## What Clarity.V does with audio

1. Captures audio from your microphone via [sounddevice](https://python-sounddevice.readthedocs.io/) (PortAudio under the hood). See [src/clarity_v/audio.py](src/clarity_v/audio.py).
2. Feeds raw audio chunks to a **local** [OpenWakeWord](https://github.com/dscripka/openWakeWord) ONNX model running on your CPU. See [src/clarity_v/wake.py](src/clarity_v/wake.py).
3. When the wake word fires, buffers audio in RAM. The buffer is a NumPy array; it never touches disk by default.
4. Sends the buffer to **local** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2 runtime). See [src/clarity_v/whisper_engine.py](src/clarity_v/whisper_engine.py). The model file lives in a local cache directory (default `~/.cache/huggingface/`).
5. Receives the transcribed text back from Whisper, runs it through hallucination filters (also local; pure Python regex — including a prompt-prefix filter and user-configurable vocabulary blacklist), and pastes it at your cursor via the OS clipboard.

**No step in this flow sends audio over the network.** The only HTTP calls Clarity.V makes during normal operation are:

- Initial Whisper model download (~1.5 GB) on first run. Configurable. After download, Clarity.V works fully offline.
- Optional Whisper model updates if you manually request them.
- Optional U.Plane integration — only if you have opted into it (see below). Default is off.

You can verify this by running Clarity.V with the network disconnected. Wake-word detection, dictation, paste — all work. Only the first-run model download will fail.

---

## What Clarity.V stores on disk

By default:

- **Whisper model**: cached in `~/.cache/huggingface/hub/` (or whatever `HF_HOME` is set to). ~1.5 GB for Medium. Shared across other Whisper-using apps on your machine.
- **OpenWakeWord ONNX files**: bundled with the package, ~5 MB each.
- **Settings**: `~/.clarity_v/settings.json`. Your preferences (colors, keybinds, active dictionary). Not audio.
  - `vocabulary_blacklist`: a comma-separated list of words or phrases the user wants stripped from transcriptions. Stored locally in `settings.json`; never transmitted.
- **Dictionaries**: bundled in `dictionaries/` + user-added files at `~/.clarity_v/dictionaries/`. Plain JSON. Not audio.

**Audio is never written to disk by default.** If you enable the optional dictation log in Settings, transcripts (not audio) are written to `~/.clarity_v/dictation_logs/dictation_log_NNN.jsonl` (JSONL, UTF-8, append-only, rotates at 500 KB per file). You control this; it's off by default.

---

## What leaves the machine

By default: **nothing**.

If you opt in to optional features, the following can leave:

### U.Plane integration *(off by default)*

If you're a [U.Plane](https://uplane.host) customer and have enabled the integration in Settings → Integrations → U.Plane:

- Dictated text is routed directly into your U.Plane instance's agent context.
- Your U.Plane instance runs **on your own machine or your own server**. It is not an external service.
- The route is a local HTTP call (`http://127.0.0.1:8001` by default) or an outbound call to your own U.Plane server if you've configured one.

This is opt-in. Disabling it stops all network traffic from Clarity.V again.

### Crash reports *(off by default)*

If Clarity.V crashes and you opt in to report it: a Python stack trace, OS info, Clarity.V version, optionally the last 10 lines of log. Sent to GitHub Issues or our crash collector. Never audio, never transcribed text.

---

## What about cloud STT?

Some forks may add cloud STT backends (Deepgram, AssemblyAI, OpenAI Whisper API, etc.). Those would change this privacy story for whichever users enable them.

**The upstream Clarity.V will not add cloud STT as a default.** Local Whisper is the entire point. A cloud STT backend behind an opt-in switch may exist eventually if a contributor PRs one, but it will be off by default, will require explicit opt-in, and the UI will say in plain language: "this sends your audio to [provider]."

---

## How to verify this yourself

1. **Read the code.** Every file in `src/clarity_v/` is plain Python. The audio paths are short and explicit. There are no obfuscated calls.

2. **Disconnect your network.** After the first-run model download, Clarity.V works fully offline. Try it — turn off Wi-Fi, dictate, see text appear. If audio were going anywhere, this wouldn't work.

3. **Monitor network traffic.** Run [Wireshark](https://www.wireshark.org/) or [Little Snitch](https://www.obdev.at/products/littlesnitch/) (macOS) or your favorite outbound-firewall tool. Filter by the Clarity.V process. Outside of model download and any optional features you've enabled, there should be no traffic.

4. **Check `~/.clarity_v/`** for anything you didn't expect. The directory layout is documented; nothing should appear that isn't listed in [Settings](src/clarity_v/settings/) or [Dictionaries](dictionaries/).

5. **`grep -r "https\?://" src/clarity_v/`** — every HTTP URL in the codebase. Most are either docstrings/comments, integration code (skipped when off), or download URLs (only on first run).

---

## Why local-first?

- **Sovereignty.** Your voice is your own. Voice data sent to a cloud STT is harvested, often used for training, often retained for longer than the provider's stated retention policy.
- **Latency.** Local STT round-trips in milliseconds. Cloud STT round-trips in hundreds of milliseconds at best. For dictation, that's the difference between a tool you forget about and a tool you fight with.
- **Cost.** You pay nothing per dictation. Cloud STT charges by the minute or by the second.
- **Reliability.** Local STT works when your internet is down. Cloud STT doesn't.
- **Proof.** A free, open, local-first dictation product is the proof that we ship real working tech for free. Cloud STT is the opposite of that proof.

---

## Reporting a privacy concern

If you find something Clarity.V does that you think shouldn't happen — a network call you weren't expecting, a file written somewhere it shouldn't be, audio kept longer than necessary — open an issue on GitHub or email the maintainer.

This is a one-person project. The author cares about this. He'll respond.

---

## License

The privacy promise is part of the MIT license that this project is shipped under. The license doesn't *enforce* the promise — that comes from the code — but the project's intent is captured in the docs you're reading.

If you fork Clarity.V and change the privacy story for your fork, document it in your own PRIVACY.md. Don't quietly add cloud STT and ship the same brand.
