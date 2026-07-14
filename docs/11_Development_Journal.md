# 11 — Development Journal

This is a chronological narrative log of development sessions — what was worked on and why, in the order it happened. It's a different thing from [../learning/](../learning/Project%20Learning.md), which is a curated, categorized reference (workflows, bugs, lessons, API notes, architecture decisions, prompt improvements) meant to be scanned by topic, not read in order. When in doubt: durable, reusable knowledge goes in `learning/`; "here's what happened, in order" goes here.

## 2026-07-11 — Initial scaffold

Project structure created (`learning/`, `docs/`, `prompts/`, `src/`, `data/`, `output/`, `images/`, `tests/`), Python virtual environment set up, Playwright with Chromium installed for browser-automation-based connectors.

## 2026-07-12 — Repo/git cleanup

Discovered and fixed a misplaced `.git` (initialized at the Windows user profile root instead of the project folder) and unresolved merge-conflict markers left in `README.md`. Reconciled local scaffold with the remote GitHub repo (`bzartstudio-oss/Rental-Agent`) via a proper merge, then pushed. Established the `CLAUDE.md` working agreement for this project. Full details in [../learning/git_notes.md](../learning/git_notes.md).

## 2026-07-13 — Documentation structure

Created the numbered `docs/` structure (this file and its siblings, `00`–`14`) to capture architecture, data model, and process decisions before implementation begins. Also created `notes/` (Ideas, Research, FutureFeatures, Questions) and confirmed the rental type (residential apartments) and `data/` subfolder layout. Split `learning/Project Learning.md` into topic files.

## 2026-07-13 — Incident: unexplained file wipe in docs/

A batch of files across `docs/`, `notes/`, `data/`, `src/`, and the project root were force-created/truncated within about a one-minute window, wiping the content of every `docs/00`–`14` file. Root cause undetermined — no scheduled task or cron job was found responsible, and the user confirmed no other session should have been active. Content was restored from this session's conversation history. See [../learning/git_notes.md](../learning/git_notes.md) and the leftover empty files (`docs/decisions/`, `CHANGELOG.md`, `PROJECT_RULES.md`, `TODO.md`, `examples/`, `scripts/`) for forensic traces if this needs further investigation.

## 2026-07-14 — V1.0 architecture: Rental Intelligence Platform

Reframed the project from a simple scraper to a self-improving research platform around 7 core principles (never lose information, permanent-database updates, versioned history, reproducible searches, extensible filters, extensible platforms/cities without redesign, business logic independent of any website). Rewrote `docs/00`–`10` with a concrete V1.0 design: SQLite as the storage engine, a Connector/Collector split, an immutable `search_results` snapshot table, a resolved legacy-`src/`-folder reconciliation plan, and a phased roadmap (storage first, second connector last, to validate the platform-independence boundary). Full decision log in [../learning/architecture_notes.md](../learning/architecture_notes.md) and [../learning/database_notes.md](../learning/database_notes.md). Also found and fixed more casualties from the 2026-07-13 file-wipe incident (`src/connectors/README.md` and several other empty `README.md` files that had gone unnoticed).
