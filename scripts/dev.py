"""
One-command developer helper.

Usage:
    python scripts/dev.py check       run lint + format-check + tests
    python scripts/dev.py fix         auto-fix lint + apply formatting
    python scripts/dev.py test        just the tests
    python scripts/dev.py lint        just the lint check
    python scripts/dev.py format      apply the formatter
    python scripts/dev.py all         everything (check + smoke imports)
    python scripts/dev.py help        show this list

Why this exists, in plain English:
Instead of remembering five different commands ("how do I run lint
again? what was the test command? do I run format before or after?"),
this script knows all of them and runs them in the right order. One
command, one answer.

It exits 0 on success, non-zero on the first failure — so you can
chain it into other tooling if you want.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PATHS = ["src/", "tests/", "tools/"]


def _run(cmd: list[str], description: str) -> bool:
    """Run a command, stream output, return True on success."""
    print(f"\n--- {description} ---")
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    ok = result.returncode == 0
    print(f"--- {description}: {'OK' if ok else 'FAIL'} ---")
    return ok


def cmd_lint() -> bool:
    return _run(
        [sys.executable, "-m", "ruff", "check"] + PATHS,
        "ruff check (lint)",
    )


def cmd_format_check() -> bool:
    return _run(
        [sys.executable, "-m", "ruff", "format", "--check"] + PATHS,
        "ruff format --check (formatting consistency)",
    )


def cmd_format() -> bool:
    return _run(
        [sys.executable, "-m", "ruff", "format"] + PATHS,
        "ruff format (apply)",
    )


def cmd_fix() -> bool:
    ok = _run(
        [sys.executable, "-m", "ruff", "check", "--fix"] + PATHS,
        "ruff check --fix (auto-fix lint)",
    )
    return cmd_format() and ok


def cmd_test() -> bool:
    return _run(
        [sys.executable, "-m", "pytest", "tests/"],
        "pytest",
    )


def cmd_check() -> bool:
    """Lint + format check + tests. The "is this clean?" entry point."""
    return cmd_lint() and cmd_format_check() and cmd_test()


def cmd_all() -> bool:
    """Everything: check + import smoke."""
    if not cmd_check():
        return False
    return _run(
        [
            sys.executable,
            "-c",
            (
                "import sys; sys.path.insert(0, 'src'); "
                "from clarity_v.app import main; "
                "print('OK: clarity-v.app.main imports')"
            ),
        ],
        "import smoke",
    )


COMMANDS = {
    "check": cmd_check,
    "fix": cmd_fix,
    "test": cmd_test,
    "lint": cmd_lint,
    "format": cmd_format,
    "all": cmd_all,
}


def show_help() -> int:
    print(__doc__)
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("help", "-h", "--help"):
        return show_help()

    name = sys.argv[1]
    if name not in COMMANDS:
        print(f"Unknown command: {name!r}")
        print(f"Available: {', '.join(COMMANDS.keys())} | help")
        return 1

    ok = COMMANDS[name]()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
