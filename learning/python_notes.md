# Python Notes

Python/environment-specific lessons and decisions for this project. See [Project Learning.md](Project%20Learning.md) for the full index.

## Lessons Learned

- **2026-07-12 — Python's `python` command was not resolving on Windows, so the environment had to be created with `py -m venv` and the venv interpreter used directly.** Fix: create the environment with `py -m venv .venv`, then use `.venv\Scripts\python.exe` for installs and execution (don't rely on `python`/`pip` resolving correctly on PATH in this environment).
