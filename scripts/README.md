# Developer scripts

These are quality-of-life helpers for working on Clarity.V. None of them are needed to *use* Clarity.V — they only matter if you're editing the code.

## `dev.py` — one command, everything

```bash
python scripts/dev.py check     # is the codebase clean?
python scripts/dev.py fix       # auto-fix what can be auto-fixed
python scripts/dev.py test      # just run the tests
python scripts/dev.py all       # check + import smoke
python scripts/dev.py help      # show the full list
```

`check` is the one you run most. It does, in this order:

1. **Lint** (`ruff check`) — catches unused imports, common bugs, style issues.
2. **Format check** (`ruff format --check`) — verifies formatting matches what the tool would produce.
3. **Tests** (`pytest`) — runs the 127 unit tests.

If anything is wrong, it stops at the first failure with a clear message.

`fix` runs `ruff check --fix` (auto-fix what ruff can) followed by `ruff format` (apply formatting). Run it before committing if you've made messy changes.

## Why bother

The same checks run on GitHub when you propose a change (see `.github/workflows/checks.yml`). Running them locally first means you catch problems before pushing, instead of pushing and waiting 2-5 minutes for CI to tell you the same thing.

If you install [pre-commit](https://pre-commit.com/) (`pip install pre-commit && pre-commit install`), all of this runs automatically every time you make a commit — see `.pre-commit-config.yaml` at the repo root.
