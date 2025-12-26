## TOOLS! 🔧
Documentation for developer tooling. NEVER run any tools outside of the **tools** directory!

### test-session
Builds a complete virtual environment (.venv) in the project root directory and launches the CLI within it. Designed for conveniently testing any local code changes. Cleans up after itself after exiting the CLI or upon crash.

Logs are generated in your user's data directory under `LocalSage/logs/` if you want to look at tracebacks.

Available for both **bash** and **fish**. Do NOT run this script if you've built your own .venv in the project root directory! It will go poof.
