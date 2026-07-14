# Playwright Notes

Playwright/browser-automation-specific lessons and decisions for this project. See [Project Learning.md](Project%20Learning.md) for the full index.

## Lessons Learned

- **2026-07-12 — Installed the Playwright browser runtime for Chromium to support web automation features.** Ran `.venv\Scripts\python.exe -m playwright install chromium`. Needed because installing the `playwright` package alone does not download the actual browser binary.

## Resources

- `src/browser/browser_manager.py` — existing (pre-dates the current `src/` structure) minimal launcher: opens Chromium non-headless via `sync_playwright()`. Not yet wired into the connector framework — see [architecture_notes.md](architecture_notes.md) for the legacy-folder reconciliation note.
