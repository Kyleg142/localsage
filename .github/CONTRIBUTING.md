# Contributing to Local Sage
Thank you for considering contributing! Expectations are quite simple. Keep changes small and focused, and do not blow up the UX.

## Expectations 📝
- **Python Version:** Dependency based, currently 3.10+.
- **Scope:** One feature or fix per PR. If it's a big change, please open an issue first.
- **Description:** A rundown on your PR.

## Code Quality 🐍
**This project uses:**
- `ruff` for linting & formatting.
- `pyright` or `basedpyright` for type checking.

**Typical checks before opening a PR:**
```bash
# Lint
ruff check .
# format
ruff format .

# Type check
pyright sage.py
# or, if you’re using basedpyright:
basedpyright sage.py
```
**Note:** You do not have to fight every type warning to the death, but don’t introduce obvious new ones for no reason. If you can’t get a clean run because of something strict, leave a short comment explaining why and move on.

## Testing 🧪
The CI pipeline **will enforce** passing tests. Before submitting, please ensure these pass locally:
```bash
# Run the full suite
pytest
```

The pipeline consists of:
- **test_sage.py**: CLI smoke tests.
- **test_sage_math_santizer.py**: Logic verification.

## In Summary...
Run `ruff`, `pyright`, and `pytest`. If all pass, you are golden! Open a PR and it will be reviewed.
