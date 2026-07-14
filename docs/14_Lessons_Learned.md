# 14 — Lessons Learned

This is the architecture/product-level counterpart to [../learning/](../learning/Project%20Learning.md). Those files are the day-to-day running log (workflows, bugs, environment issues, API quirks) and are the first place to check. This doc is for lessons specifically about *how this system should be designed* — the kind of insight that should change a decision recorded in `docs/01`–`09`, not just a one-off fix.

## 2026-07-13 — Don't force-create files without checking for existing content

A batch file-creation operation truncated every file in `docs/00`–`14` to zero bytes by force-creating paths that already had real content (see [11_Development_Journal.md](11_Development_Journal.md)). Whatever tool/script did this used an "ensure file exists" pattern that overwrites rather than skips. Lesson: any future automated scaffolding (scripts, generators) run against this repo must check whether a target file already has content before writing to it — never blindly force-create over an existing path.

## Format for future entries

```
### YYYY-MM-DD — Short title

What we assumed → what we found → what changed as a result (and which doc(s) were updated).
```
