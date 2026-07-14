# Git Notes

Git/GitHub-specific lessons and decisions for this project. See [Project Learning.md](Project%20Learning.md) for the full index.

## Decisions

- **Remote repo is `bzartstudio-oss/Rental-Agent`**, not `BZStudio/Rental-Agent`. The `BZStudio` org doesn't exist under the authenticated GitHub account. Always verify with `gh repo view <owner>/<repo>` before assuming an org/user name.

## Lessons Learned

- **2026-07-12 — `.git` was accidentally initialized at the Windows user profile root (`C:\Users\BZ`) instead of inside the project folder.** This put the entire home directory (Documents, Downloads, AppData, browser data, registry hives, etc.) inside a git working tree with a real GitHub remote attached. No commits existed yet, so nothing leaked, but a careless `git add -A` from the wrong directory could have staged and pushed the whole home folder. Fix: always confirm `git rev-parse --show-toplevel` (or check where `git status` resolves `.git` to) matches the intended project folder before running any git command in a new environment, especially right after `git init`.
- **2026-07-12 — `README.md` contained literal, unresolved merge-conflict markers (`<<<<<<< HEAD` / `=======` / `>>>>>>>`) with no corresponding git merge history.** Root cause: GitHub had auto-created the remote repo with its own bare `README.md`, and at some point local content was merged/pasted against it without ever finishing the merge. Fix: resolved by re-running a real `git merge origin/main --allow-unrelated-histories`, keeping the fuller local README content, and committing the resolution — rather than leaving hand-pasted conflict markers in a tracked file.
- **2026-07-12 — Added `.venv/` to `.gitignore`.** A virtualenv had already been created in the project folder before git tracking was set up correctly, and would otherwise have been committed. See [python_notes.md](python_notes.md) for the venv creation details.
- **2026-07-13 — Uncommitted work was vulnerable to being silently destroyed.** Between the initial merge/push and this date, every `docs/` file (plus `notes/`, `data/`, `src/` subfolder additions and `learning/` topic files) had been created but never committed. An unexplained batch operation then force-created/truncated ~40 files across the project within about a minute, wiping all 15 `docs/00`–`14` files (see [architecture_notes.md](architecture_notes.md) for the incident details). Content was recoverable only because it was still present in an active session's conversation history — if that session had ended first, it would have been unrecoverable. Fix: commit meaningful work promptly rather than leaving it uncommitted for extended periods; don't treat "not yet asked to commit" as a reason to let hours of work sit only on disk.

## Resources

- Remote repo: https://github.com/bzartstudio-oss/Rental-Agent
