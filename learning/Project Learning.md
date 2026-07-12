# Project Learning

## Goals

## Key Decisions

- **Canonical project location is `Clients/Rental-Agent`.** An earlier duplicate scaffold at `Clients/Agent Rental/Rental-Agent` was created by mistake and has been removed — its content had already been moved into the real folder before that was noticed.
- **Remote repo is `bzartstudio-oss/Rental-Agent`**, not `BZStudio/Rental-Agent`. The `BZStudio` org doesn't exist under the authenticated GitHub account; always verify with `gh repo view <owner>/<repo>` before assuming an org/user name.

## Lessons Learned

- **2026-07-12 — `.git` was accidentally initialized at the Windows user profile root (`C:\Users\BZ`) instead of inside the project folder.** This put the entire home directory (Documents, Downloads, AppData, browser data, registry hives, etc.) inside a git working tree with a real GitHub remote attached. No commits existed yet, so nothing leaked, but a careless `git add -A` from the wrong directory could have staged and pushed the whole home folder. Fix: always confirm `git rev-parse --show-toplevel` (or check where `git status` resolves `.git` to) matches the intended project folder before running any git command in a new environment, especially right after `git init`.
- **2026-07-12 — `README.md` contained literal, unresolved merge-conflict markers (`<<<<<<< HEAD` / `=======` / `>>>>>>>`) with no corresponding git merge history.** Root cause: GitHub had auto-created the remote repo with its own bare `README.md`, and at some point local content was merged/pasted against it without ever finishing the merge. Fix: resolved by re-running a real `git merge origin/main --allow-unrelated-histories`, keeping the fuller local README content, and committing the resolution — rather than leaving hand-pasted conflict markers in a tracked file.
- Added `.venv/` to `.gitignore` — a virtualenv had already been created in the project folder before git tracking was set up correctly, and would otherwise have been committed.
- **2026-07-12 — Python's `python` command was not resolving on Windows, so the environment had to be created with `py -m venv` and the venv interpreter used directly.** Fix: create the environment with `py -m venv .venv`, then use `.venv\Scripts\python.exe` for installs and execution.
- **2026-07-12 — Installed Playwright browser runtime for Chromium to support web automation features.** Fix: ran `.venv\Scripts\python.exe -m playwright install chromium`.

## Resources

- Remote repo: https://github.com/bzartstudio-oss/Rental-Agent
