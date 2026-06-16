"""
Commit listener — the post-paste voice-command window.

After the main message is transcribed and pasted, Clarity.V keeps
recording for a short window (default 5 s) so the Person can issue a
voice command like "send" / "enter" / "new paragraph" without touching
the keyboard.

This is NOT done via the wake detector. OpenWakeWord can only fire on
phrases it has trained models for. The command vocabulary is open and
configurable from the dictionary, so we use a second Whisper pass on
the post-paste audio buffer and string-match the transcript against
the dictionary's voice_commands (phase="after").

See ARCHITECTURE.md § "The two voice-input mechanisms" for the full
explanation of why wake-vs-Whisper is split this way.

Public API:
    matched = run_commit_window(engine)

Returns True if a voice command fired, False otherwise. Either way the
engine should transition back to IDLE afterward (the caller handles
that).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from clarity_v.audio import concat
from clarity_v.state import State

if TYPE_CHECKING:
    from clarity_v.dictation import DictationEngine


def run_commit_window(engine: DictationEngine) -> bool:
    """Run the post-paste commit-listening window.

    Captures audio for `engine.config.commit_window_seconds` seconds,
    transcribes (beam_size=1 for speed — utterances here are short),
    runs the filter chain, and looks up `phase="after"` voice commands
    in the dictionary.

    Returns:
        True if a voice command matched and was dispatched.
        False if the window expired with no match (or empty audio).
    """
    if not engine.config.in_dictation_commands_enabled:
        print("[Commit] In-dictation/voice commands are disabled. Skipping commit window.")
        return False

    window_s = engine.config.commit_window_seconds
    print(f"[Commit] Listening for action word ({window_s:.0f}s window)...")

    engine.audio.begin_record()
    deadline = time.monotonic() + window_s
    cancelled = False
    
    last_transcribe_time = time.monotonic()
    
    while time.monotonic() < deadline:
        if engine.state.state != State.COMMIT_WAITING:
            cancelled = True
            break
            
        time.sleep(0.1)
        
        # Check for command every ~0.4s to be snappy without burning CPU
        now = time.monotonic()
        if now - last_transcribe_time >= 0.4:
            last_transcribe_time = now
            
            with engine.audio._lock:
                chunks_so_far = list(engine.audio._buffer)
                
            if not chunks_so_far:
                continue
                
            audio_so_far = concat(chunks_so_far)
            duration_so_far = len(audio_so_far) / 16000
            
            if duration_so_far < 0.3:
                continue
                
            # Fast transcribe — beam_size=1
            result = engine.whisper.transcribe(
                audio_so_far,
                beam_size=1,
                wake_phrases=engine._wake_phrases,
            )
            
            if result.text:
                command = engine.dictionary.match_voice_command(result.text, phase="after")
                if command is not None:
                    print(f"[Commit] Heard early: {result.text!r}")
                    if engine.state.state != State.RECORDING:
                        engine.audio.end_record()  # clean up buffer
                    return _dispatch_command(engine, command, source_text=result.text)

    if cancelled:
        if engine.state.state != State.RECORDING:
            engine.audio.end_record()
        print("[Commit] Window interrupted.")
        return False

    # Window expired naturally
    if engine.state.state != State.RECORDING:
        engine.audio.end_record()
    print("[Commit] Window expired without matching an action word.")
    return False


def _dispatch_command(
    engine: DictationEngine,
    command: dict,
    source_text: str,
) -> bool:
    """Execute a matched voice command via the platform adapter.

    Supported action types (see dictionaries/default.json):
        - submit         → send Ctrl+Enter
        - key            → send the literal combo in command["keys"]
        - insert         → type/paste the text in command["text"]
        - end_dictation  → no-op here (this command is phase=during,
                           shouldn't reach the after-phase matcher;
                           treated as a successful catch-all)
    """
    action = command.get("action")
    print(f"[Commit] Action: {action!r} from {source_text!r}")

    try:
        if action == "submit":
            engine.platform.send_key_combo("ctrl+enter")
        elif action == "key":
            keys = command.get("keys") or []
            engine.platform.send_key_combo("+".join(keys))
        elif action == "insert":
            text = command.get("text", "")
            if text:
                engine.platform.paste_text(text)
        elif action == "end_dictation":
            pass  # phase mismatch but harmless
        else:
            print(f"[Commit] Unknown action {action!r} — ignored.")
            return False
    except Exception as e:
        print(f"[Commit] Dispatch failed: {type(e).__name__}: {e}")
        return False

    return True
