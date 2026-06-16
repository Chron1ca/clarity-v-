"""
Voice-test launcher — walks through every interactive verification in order.

You run ONE command:

    python tools/run_voice_tests.py

It then guides you through each test, in sensible order, with clear
"what to do" instructions and generous time per attempt. You can skip
any test you don't want to do right now (just answer 'n' when asked).

What it covers:

  1. Presence visual            — see the glow bar cycle colors
  2. Whisper fixtures           — record 2 short clips (EN + PT, ~10 s each)
  3. Whisper verification       — auto, no speaking (uses fixtures from 2)
  4. Wake word detection        — say "see vee go", 3 attempts × 15 s
  5. Full dictation end-to-end  — wake + speak + paste into Notepad
  6. (Optional) Personal voice  — 25 takes for custom wake-word training

Total time (skipping the optional step): ~5-10 minutes including
Whisper model load on first run.

If any test fails, you'll see what went wrong and have the option to
retry the same test, skip ahead, or abort the whole session.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def _section(n: int, total: int, name: str, desc: str) -> None:
    print()
    print("=" * 72)
    print(f"  Step {n}/{total} — {name}")
    print("=" * 72)
    print(desc.rstrip())
    print()


def _ask_yes_no(question: str, default_yes: bool = True) -> bool:
    suffix = " [Y/n]: " if default_yes else " [y/N]: "
    while True:
        ans = input(question + suffix).strip().lower()
        if not ans:
            return default_yes
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("  Please answer y or n.")


def _wait_for_enter(prompt: str = "Press Enter when ready...") -> None:
    input(prompt)


def _run(tool: str, *args: str) -> int:
    """Run a tool script; return its exit code."""
    cmd = [sys.executable, str(REPO_ROOT / "tools" / tool), *args]
    print(f"\n>>> Running: python tools/{tool} {' '.join(args)}\n")
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


# ─── Individual steps ──────────────────────────────────────────────────


def step_presence(n: int, total: int) -> bool | None:
    _section(
        n,
        total,
        "Presence: glow bar + tray icon",
        """
        WHAT WE'RE TESTING:
          The thin colored bar at the top of your screen and the system
          tray icon. They cycle through 5 colors (idle / recording /
          processing / commit_waiting / error). You drive the pace by
          pressing Enter in the console; no arbitrary timers.

        WHAT YOU DO:
          1. Press Enter to start. Watch the top of your screen.
          2. After it finishes, the script asks if you saw the bar
             change colors. Answer y or n.

        DURATION: about 30 seconds.
        """,
    )
    if not _ask_yes_no("Run this test now?"):
        return None
    return _run("verify_presence.py") == 0


def step_fixtures(n: int, total: int) -> bool | None:
    _section(
        n,
        total,
        "Whisper fixtures: record 2 short clips (EN + PT)",
        """
        WHAT WE'RE TESTING:
          Recording two ~5-second voice samples (English + Portuguese)
          that the next step uses to verify Whisper transcribes both
          languages correctly without language pinning.

        WHAT YOU DO:
          1. Press Enter when prompted, then speak naturally.
          2. You'll be prompted TWICE — once for English, once for
             Portuguese. Each clip is 5 seconds.

        SUGGESTED PHRASES (or use your own natural speech):
          English:    "Hello, this is a test of the Clarity.V dictation system."
          Portuguese: "Olá, isto é um teste do sistema de ditado Clarity.V."

        DURATION: about 30 seconds.
        """,
    )
    if not _ask_yes_no("Run this now?"):
        return None
    return _run("record_fixtures.py") == 0


def step_whisper_verify(n: int, total: int) -> bool | None:
    _section(
        n,
        total,
        "Whisper engine verification (no speaking)",
        """
        WHAT WE'RE TESTING:
          Loads Whisper Medium (~1.5 GB; downloads on first run, then
          cached forever). Runs it against the two fixture WAVs from
          the previous step. Asserts:
            - English fixture transcribes with language='en' detected
            - Portuguese fixture transcribes with language='pt' detected
            - Silence input produces empty output (filter chain works)

        WHAT YOU DO:
          Nothing. This is automatic.

        DURATION: 1-3 minutes (longer on first run because of the model
        download).
        """,
    )
    if not _ask_yes_no("Run this now?"):
        return None
    return _run("verify_whisper.py") == 0


def step_wake(n: int, total: int) -> bool | None:
    _section(
        n,
        total,
        "Wake word detection: 'see vee go'",
        """
        WHAT WE'RE TESTING:
          The OpenWakeWord detector fires when you say the wake phrase.

          v1 ships with two trained models: cv_go (start dictation,
          spoken "see vee go") and cv_over (end dictation, spoken
          "see vee over"). This step tests cv_go.

        WHAT YOU DO:
          You get 3 ATTEMPTS, each with a 15-second window. As soon
          as one fires, the test PASSES.

          On each attempt:
            1. Press Enter when prompted.
            2. Wait ~1 second (for the listener to start).
            3. Say "see vee go" clearly. Don't whisper.
            4. If the detector fires, you'll see [DETECT] in green.

        DURATION: up to 1 minute (less if it fires first try).
        """,
    )
    if not _ask_yes_no("Run this now?"):
        return None
    return _run("verify_wake.py") == 0


def step_dictation_e2e(n: int, total: int) -> bool | None:
    _section(
        n,
        total,
        "Full dictation end-to-end (with Notepad)",
        """
        WHAT WE'RE TESTING:
          The whole pipeline — wake → record → transcribe → paste into
          a real app — works end-to-end.

        WHAT YOU DO:
          1. BEFORE pressing Enter: open Notepad (or any text editor)
             and click in the text area so the cursor is there.
          2. Press Enter to start. You have a 90-second window.
          3. Say "see vee go".
          4. Speak a sentence: "hello this is a test message".
          5. Stop talking. After ~2.5 s of silence, the recording ends.
          6. Watch Notepad: the transcription should appear at the cursor.
          7. (Optional, within 5 s of paste) Say "send" → Ctrl+Enter
             fires automatically.
          8. The script asks if the transcription appeared. Answer y or n.

        DURATION: 1-2 minutes.
        """,
    )
    if not _ask_yes_no("Run this now?"):
        return None
    return _run("verify_dictation.py") == 0


def step_personal_voice(n: int, total: int) -> bool | None:
    _section(
        n,
        total,
        "(OPTIONAL) Personal voice samples for custom wake-word training",
        """
        WHAT THIS DOES:
          Records you saying the wake phrase 25 times. Each take is
          followed by 20 auto-generated variants (pitch shift, time
          stretch, light noise) -> ~500 personal samples total. These
          go into the wake-word training pipeline so when you train a
          custom wake word, the model is biased toward YOUR voice in
          YOUR room with YOUR mic.

        WHEN TO RUN THIS:
          Only if you're ready to train a custom wake word. The
          training run itself is multi-hour and requires a separate
          venv (see TRAINING.md). The samples step is just data
          collection — but it's still 25 takes × ~5 s each ≈ 5-10
          minutes of your time.

        DURATION: 5-10 minutes. Skip with 'n' if not now.
        """,
    )
    if not _ask_yes_no("Run this now?", default_yes=False):
        return None
    print()
    phrase = input("    Wake phrase to record (default 'cv go'): ").strip()
    if not phrase:
        phrase = "cv go"
    # --model-name defaults inside the script to a safe transform of
    # --phrase (so "cv go" -> cv_go), matching train.py's contract.
    return _run("training/record_personal_voice.py", "--phrase", phrase) == 0


# ─── Main flow ─────────────────────────────────────────────────────────


STEPS = [
    ("Presence", step_presence),
    ("Fixtures", step_fixtures),
    ("Whisper", step_whisper_verify),
    ("Wake", step_wake),
    ("Dictation E2E", step_dictation_e2e),
    ("Personal voice (optional)", step_personal_voice),
]


def main() -> int:
    # UTF-8 console for unicode output (PT characters in fixtures, arrows).
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    print()
    print("=" * 72)
    print("  Clarity.V voice-test session")
    print("=" * 72)
    print("""
This walks you through every voice test in order. You can skip any
step you don't want to run right now (answer 'n').

If a step fails, you can retry it without restarting the whole session.

Total time (excluding the optional last step): about 5-10 minutes
on a machine where Whisper Medium is already cached. First-run on a
fresh machine adds ~5 min for the Whisper download (one-time).

What you'll need:
  - A working microphone (already verified)
  - Notepad (or any text editor) for the end-to-end step
  - About 10 minutes of focus

Ready? Let's go.
""")
    _wait_for_enter("Press Enter to begin (or Ctrl+C to abort)... ")

    results: dict[str, str] = {}

    for i, (name, step_fn) in enumerate(STEPS, start=1):
        while True:
            outcome = step_fn(i, len(STEPS))
            if outcome is None:
                results[name] = "SKIPPED"
                break
            if outcome is True:
                results[name] = "PASS"
                break
            # Failed.
            print()
            print(f"  Step {i} ({name}) reported a problem.")
            if _ask_yes_no("    Retry?", default_yes=True):
                continue
            results[name] = "FAIL"
            break
        time.sleep(0.5)

    print()
    print("=" * 72)
    print("  Session summary")
    print("=" * 72)
    for name, result in results.items():
        symbol = {
            "PASS": "[OK]   ",
            "FAIL": "[FAIL] ",
            "SKIPPED": "[skip] ",
        }[result]
        print(f"  {symbol} {name}")
    print()
    fails = [n for n, r in results.items() if r == "FAIL"]
    if fails:
        print(f"  {len(fails)} step(s) failed: {', '.join(fails)}")
        print("  Re-run this script and retry just those steps when ready.")
        return 1
    print("  All requested steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
