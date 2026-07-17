# 39 — Tag Readiness Report: v2.5.0-rc1

Version 2.5 Step 18 ("Release Candidate Finalization, Tagging & Pilot
Preparation"). Records every check performed before creating the local
annotated tag `v2.5.0-rc1`, per that mission's Phase 7. This is a point-in-
time record — it is written before the Phase 8 finalization commit, and its
final status line is updated after Phase 8/9 complete.

## Verified Branch

`release/v2.5-rc1` — confirmed via `git branch --show-current`.

## Verified Commit (Pre-Finalization)

`2137ff6c0ec1ffd5710ba880729171a7f2440ff2` ("Version 2.5 Step 17 - Release
Candidate Acceptance") — confirmed via `git rev-parse HEAD` and `git log -1`.
**This is not the tag target.** Per this mission's own Phase 8/9
instructions, the tag targets the Step 18 finalization commit created on top
of this one, not this commit itself.

## Clean-Tree Status

`git status --porcelain` showed exactly one untracked entry before this
step's work began: `project_review.txt`. No tracked file was modified.

## Treatment of `project_review.txt`

Inspected directly: it is a garbled Windows `tree /f` directory listing of
the entire `.venv/` package tree (UTF-16-as-UTF-8 misencoded, ~1500 lines),
unrelated to application runtime, release packaging, or any documentation
requirement in this mission. Selected action: **added to `.gitignore`**
(rather than deleted) since it predates this session and its origin/purpose
outside this conversation is unknown — the safer, non-destructive choice.
Its contents were never staged or committed.

## Final Test Result

`python -m unittest discover -s tests -t .` (pytest is not a project
dependency — `requirements.txt` has never included it, and every other Step
17/18 test run uses `unittest`; `python -m pytest -q` would fail with
`ModuleNotFoundError` on a clean install, so `unittest discover` was used
as the equivalent, actually-installed verification the mission's Phase 2
intends):

```
Ran 1308 tests in 256.680s

OK
```

**1308 tests, 0 failures, 0 errors, 0 skipped.**

## Health-Check Result

`python scripts/health_check.py --json` — **13/13 PASS**, 0 WARN, 0 FAIL.
(`notification_channels` reports `enabled=['console', 'file']`,
`not-yet-configured=['email', 'webhook']` — expected, not a failure.)

## Secret-Scan Result

`git grep` across every tracked file (`.venv/` is untracked and excluded)
for API-key/secret/password/token/private-key-style assignments, `BEGIN
...PRIVATE KEY` blocks, and `Bearer <token>` literals: **zero matches**.
`.env` is not tracked (only `.env.example`, which contains variable names
and no values). `data/.web_secret_key` is not tracked. No secret value was
printed during this scan — only file/line locations were inspected, and none
were found.

## Migration Result

11 migrations present under `src/storage/migrations/`
(`0001_v2_knowledge_engine.sql` through `0011_web_dashboard.sql`);
`scripts/health_check.py`'s own `migration_status` check confirms all 11 are
applied to the local database with none pending.

## Startup Checks

- **Flask dashboard**: `create_app()` + Flask's in-process test client —
  `GET /` returned `200`, `GET /api/v1/health` returned `200`.
- **CLI**: `python -m src.ui.cli --help` exited `0`.
- **Script `--help`**: `backup.py`, `restore.py`, and `verify_backup.py` all
  printed correct usage text and exited `0`.

## Backup/Restore Checks

`tests/scripts/test_backup_restore.py` — 10/10 passing (creation +
manifest, secrets never included, compressed archive, fresh-backup verifies
OK, corrupted-file detected, preview-without-writing, restore-to-alternate-
location, restored-database-starts-up, refuses-overwrite-without-force,
historical-data-preserved). No generated database, media, raw pages,
report, or backup artifact is tracked by git — confirmed via
`git ls-files` filtered for `*.db`, `data/media/`, `data/raw_pages/`,
`backups/`, `output/` (excluding `.gitkeep` placeholders): all clean.

## Manifest Result

`release/v2.5.0-rc1-manifest.json` created (Phase 3) with version, migration
list, test/health/acceptance/security/backup results, supported interfaces,
fixture-tested/live-tested/provider-dependent capability lists, known
limitations, and included documentation. Its `commit_hash` and
`document_checksums_sha256` fields are placeholders pending the Phase 8
finalization commit (a manifest cannot correctly checksum documents or cite
a commit hash that doesn't exist yet) — updated immediately before that
commit is made.

## Pilot Configuration Result

`config/pilot.example.json` created (Phase 4): valid JSON, contains no
credentials, every field verified against the real `FilterRegistry` filter
keys, `RankingProfile` names, and `FeedbackMode` values in `src/`. Explicitly
labels `walking_distance`/`public_transport_time` as an estimate (proximity
score, not literal minutes) and documents that no config-file loader exists
in this release — the file is a manual-entry reference, not an executable
input.

## Documentation Result

- `docs/37_Pilot_Operations_Guide.md` — created, 23 sections, every command
  verified against real CLI argument lists (`src/ui/*.py`) and existing
  docs/30/31/35.
- `docs/38_Pilot_Feedback_Template.md` — created, all required structured
  fields present.
- `docs/39_Tag_Readiness_v2.5.0-rc1.md` — this document.
- Pre-existing release documents (`docs/33`-`docs/36`, `MASTER_SPEC.md`,
  `RELEASE_NOTES_v2.5-rc1.md`, `CHANGELOG.md`, `VERSION`) re-verified present
  and internally consistent with `release_manifest.json` (Step 17's own
  manifest) and this step's new manifest.

## Remaining Release Blockers

**None identified.** No `FAIL` from the health check, no test failure, no
secret found, no untracked generated artifact staged, no undocumented or
overstated capability found in `RELEASE_NOTES_v2.5-rc1.md` or
`MASTER_SPEC.md`. `project_review.txt` was the only anomaly found and it has
been fully resolved (see above).

## Tag Recommendation

**GO**, conditional on Phase 8 completing cleanly: create the Phase 8
finalization commit ("Finalize v2.5.0-rc1 release and pilot materials"),
re-run the full test suite against that commit, and — only if that re-run is
also 0 failures/0 errors — create the local annotated tag `v2.5.0-rc1`
pointing at the finalization commit (not this report's verified commit
above). Do not push the tag; do not merge `release/v2.5-rc1` into `main` or
`platform-v1`. See the Step 18 final report for the finalization commit hash
and tag confirmation.

## Related Documents

- [33_Release_Candidate_Acceptance.md](33_Release_Candidate_Acceptance.md)
- [34_Security_Acceptance.md](34_Security_Acceptance.md)
- [35_Installation_and_Operations.md](35_Installation_and_Operations.md)
- [37_Pilot_Operations_Guide.md](37_Pilot_Operations_Guide.md)
- [../release/v2.5.0-rc1-manifest.json](../release/v2.5.0-rc1-manifest.json)
