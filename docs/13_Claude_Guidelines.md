# 13 — Claude Guidelines

This doc is the documentation-specific companion to the project's [CLAUDE.md](../CLAUDE.md) working agreement — that file is the source of truth for *how* Claude should operate in this project generally (explain everything for a new employee, never skip steps, production-quality code, always say which file and why, always update the learning log). This doc adds conventions specific to the `docs/` folder.

## Numbering Convention

Files in `docs/` are numbered `00`–`14` and read roughly in dependency order: vision and architecture first, then the pipeline stages in the order data flows through them (Search Request → Platform Discovery → Connector Framework → Analysis Engine → Ranking → Report), then process docs (Roadmap, Journal, Glossary, these guidelines, Lessons Learned).

If a new doc is needed, give it the next free number rather than inserting decimals (`14a`, etc.) — renumber the tail if it must go in the middle, and update every cross-reference.

## When a Doc Is "Draft" vs. Settled

Every doc created so far is marked `Status: Draft` at the top with explicit `*TBD*` markers on undecided points. When a decision is actually made:

1. Replace the `*TBD*` with the real answer.
2. Remove the "Status: Draft" line once the whole doc reflects reality (or narrow it, e.g. "Status: Confirmed except Ranking Criteria").
3. Record *why* the decision was made in the relevant [../learning/](../learning/Project%20Learning.md) topic file — the doc says *what*, the learning log says *why and when*.

## Cross-Referencing

Link to other docs with relative Markdown links (e.g. `[06_Connector_Framework.md](06_Connector_Framework.md)`) rather than restating their content. If the same fact needs updating in two places, it will drift.

## Keeping Docs Honest

Never write a doc section as if a decision were made when it wasn't — an invented "we chose X" is worse than an honest `*TBD*`, because it will silently steer future implementation in the wrong direction. This is the same principle behind the "no assumptions" rule in [CLAUDE.md](../CLAUDE.md).
