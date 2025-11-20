# Contributing to Local Sage
Thank you for considering contributing! Expectations are quite simple. Keep changes small and focused, and do not blow up the UX.

## Python Version 🐍
Local Sage currently targets **Python 3.9+**.

If you’re submitting code, make sure it at least runs on 3.9.

## Code Style
**This project uses:**
- **ruff** for linting & formatting
- **pyright** / **basedpyright** for type checking

**Typical checks before opening a PR:**
```bash
# Lint
ruff check sage.py
# format
ruff format sage.py

# Type check
pyright sage.py
# or, if you’re using basedpyright:
basedpyright sage.py
```
You do not have to fight every type warning to the death, but don’t introduce obvious new ones for no reason. If you can’t get a clean run because of something strict, leave a short comment explaining why and move on.

## Pull Request Guidelines
Keep PRs **small and focused**, one feature/fix per PR. For large features or changes, open an issue first for discussion.

#### To get started:
1. Fork the repo.
2. Clone your fork.
3. Create a branch, commit your changes, and push.
4. Open a PR to `main` on the original repo.

#### In your PR description, include:
1. What problem this solves.
2. What has changed.
3. How you tested the change (commands & environment).
