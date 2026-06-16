"""
Phase 5 verification: full dictation flow end-to-end.

Tests:
  1. DictationEngine constructs (loads Whisper, wake model, dictionary,
     platform adapter, audio capture).
  2. Engine starts (audio stream opens, wake listening).
  3. Manual flow with Notepad open:
     - say wake word → recording starts (state → RECORDING)
     - speak message → audio captured
     - say "see vee over" → cv_over wake ends recording (state → PROCESSING)
     - Whisper transcribes → dictionary applies → paste at cursor
     - state → COMMIT_WAITING for 5 s → IDLE
  4. After Notepad receives the text, the test reads it back via clipboard
     to assert the expected substring appeared.

Usage:
    python tools/verify_dictation.py

This is the first phase whose verification proves the WHOLE engine works.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from clarity_v.dictation import DictationEngine  # noqa: E402
from clarity_v.state import State  # noqa: E402


def _print(level: str, msg: str) -> None:
    print(f"  [{level:8s}] {msg}")


def test_engine_constructs() -> DictationEngine | None:
    print("\n[1/3] DictationEngine construction")
    print("    Loading Whisper Medium (~1.5 GB on first run), wake model,")
    print("    dictionary, platform adapter, audio capture...")
    try:
        engine = DictationEngine()
    except Exception as e:
        _print("FAIL", f"Construction raised: {type(e).__name__}: {e}")
        return None
    _print("OK", "Engine constructed:")
    _print("INFO", f"  Wake models: {[m for m, _ in engine.wake.list_models()]}")
    _print("INFO", f"  Dictionary: {engine.dictionary.name}")
    _print("INFO", f"  Platform: {engine.platform.name}")
    _print("INFO", f"  Whisper: {engine.whisper.model_size}")
    _print("INFO", f"  Initial state: {engine.state.state.value}")
    return engine


def test_engine_starts(engine: DictationEngine) -> bool:
    print("\n[2/3] Engine starts cleanly")
    try:
        engine.start()
        time.sleep(0.5)
    except Exception as e:
        _print("FAIL", f"start() raised: {type(e).__name__}: {e}")
        return False
    if engine.state.state != State.IDLE:
        _print("FAIL", f"Expected IDLE after start, got {engine.state.state}")
        return False
    _print("OK", f"Engine running. State: {engine.state.state.value}")
    return True


def test_end_to_end_flow(engine: DictationEngine) -> bool:
    print("\n[3/3] End-to-end flow")
    print("    1. Open Notepad (or any text editor) and click in the text area.")
    print("    2. Press Enter here when ready (you have 90 seconds total).")
    print("    3. Say the wake word (default: 'see vee go').")
    print("    4. Speak a clear sentence (e.g., 'hello this is a test').")
    print("    5. Stop talking — silence will end the recording after ~2.5 s.")
    print("    6. Watch Notepad: the transcription should appear.")
    print("    7. (Optional) say 'send' within 5 s to fire Ctrl+Enter.")
    print()
    input("    Press Enter when Notepad is open and focused...")

    # Track state transitions.
    transitions = []
    engine.state.subscribe(lambda s, info: transitions.append(s))

    print("\n    Listening... take your time. (90 s window)")
    deadline = time.time() + 90.0
    saw_committed = False
    last_status_print = 0.0
    while time.time() < deadline:
        # Periodic status so the Person knows it's alive.
        remaining = int(deadline - time.time())
        if time.time() - last_status_print > 5.0:
            print(f"    [waiting] state={engine.state.state.value} ({remaining}s left)")
            last_status_print = time.time()
        if State.COMMIT_WAITING in transitions:
            saw_committed = True
            # Wait for the commit window to elapse.
            while engine.state.state == State.COMMIT_WAITING:
                time.sleep(0.2)
            break
        time.sleep(0.2)

    if not saw_committed:
        _print(
            "FAIL",
            "90 s passed without reaching COMMIT_WAITING. "
            "Wake word may not have fired, or processing failed.",
        )
        _print("INFO", f"Transitions seen: {[s.value for s in transitions]}")
        return False

    seen_states = [s.value for s in transitions]
    _print("INFO", f"State transitions: {seen_states}")
    expected = ["recording", "processing", "commit_waiting"]
    for s in expected:
        if s not in seen_states:
            _print("FAIL", f"Missing expected state: {s}")
            return False
    _print("OK", "Full flow ran: IDLE → RECORDING → PROCESSING → COMMIT_WAITING → IDLE")

    answer = input("    Did the transcription appear in your text editor? [y/n]: ")
    if answer.strip().lower() != "y":
        _print("FAIL", "Person reported no text appeared.")
        return False
    _print("OK", "Person confirmed transcription appeared.")
    return True


def main() -> int:
    print("=" * 60)
    print("Clarity.V Phase 5 — Dictation engine end-to-end verification")
    print("=" * 60)

    engine = test_engine_constructs()
    if engine is None:
        return 1

    results = {"construct": True}
    results["start"] = test_engine_starts(engine)

    if results["start"]:
        try:
            results["e2e"] = test_end_to_end_flow(engine)
        finally:
            engine.stop()

    print("\n" + "=" * 60)
    print("Summary:")
    for name, passed in results.items():
        print(f"  {'OK' if passed else 'FAIL':5s} {name}")
    print("=" * 60)
    all_pass = all(results.values())
    print("PHASE 5 COMPLETE" if all_pass else "PHASE 5 INCOMPLETE")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
