# 15 — Agent Architecture

Status: Designed 2026-07-14 — not a new module to build now, a naming/boundary
convention the rest of the v2.0 design already follows. Requirement 10: prepare for
Discovery, Research, Analysis, Learning, Report, and Notification agents; only Discovery
and Research need to exist today.

## What "Agent" Means Here

Not a forced common base class or message-passing framework — building that now, before
a second agent needs to run independently (in a separate process, on a separate
schedule), would be exactly the kind of premature abstraction [CLAUDE.md](../CLAUDE.md)
warns against. An "agent" in this architecture is **a bounded responsibility with a
clean, already-isolated input/output contract** — every stage introduced since v1.0
already has this property (that's what the module boundaries in
[01_System_Architecture.md](01_System_Architecture.md) were for). What v2.0 adds is
naming that isolation explicitly as "agent shape," so wrapping a stage in a real,
independently-callable `Agent` object later is a thin refactor, not a redesign.

## Mapping: Six Agents, Two Built

| Agent | Responsibility | Current code | Status |
|---|---|---|---|
| **Discovery Agent** | Know what platforms exist, keep their metadata current | `discovery/discovery_agent.py::DiscoveryAgent` | **Built** (v1.1) |
| **Research Agent** | Given a request, fetch raw listings from available platforms | `core/agent.py::RentalResearchAgent` (fetch portion of `run()`) | **Built**, but see "Research Agent Today Is Doing Too Much" below |
| **Analysis Agent** | Normalize, version, and enrich raw listings into `Apartment` + `apartment_analysis_metrics` | `analyzers/engine.py::process_listings` + Deep Analysis Engine ([07_Analysis_Engine.md](07_Analysis_Engine.md)) | Logic exists as plain functions; not yet wrapped as an independently-callable agent |
| **Learning Agent** | Turn search outcomes into Knowledge Engine observations and Platform Intelligence rollups | `knowledge/engine.py` ([16_Knowledge_Engine.md](16_Knowledge_Engine.md)) | Designed, not yet built at all |
| **Report Agent** | Turn ranked results into a deliverable | `services/report_generator.py::generate_report` | Logic exists as a plain function; not yet wrapped as an independently-callable agent |
| **Notification Agent** | Tell someone a search finished / something noteworthy changed | — | Not designed yet — genuinely future, no code or schema reserved beyond the general append-only pattern already established |

Four of six responsibilities already have real, working code — they're just invoked as
function calls from inside `RentalResearchAgent.run()` today rather than as objects with
their own lifecycle. That gap (function call vs. independent object) is the entire
distance left to "support adding the others."

## Research Agent Today Is Doing Too Much

`RentalResearchAgent.run()` currently does five things in sequence: persist the request,
fetch (Research Agent's real job), hand off to Analysis, hand off to Ranking, hand off to
Report. That's fine for v1.0/v1.1 — two real agents, no need for more structure yet. It
stops being fine once a Learning Agent and Notification Agent are added: `run()` would
keep growing by one more inline step per agent, until "the orchestrator" and "the
Research Agent" are indistinguishable and every new capability means editing the one
function everything else already depends on.

**The refactor this implies (later, not now):** `RentalResearchAgent` narrows to just its
actual Research Agent job (query connectors, return raw listings) plus **coordination** —
calling out to Analysis/Ranking/Report/Learning/Notification as separate steps it
sequences but doesn't implement. This is explicitly deferred — see
[10_Roadmap.md](10_Roadmap.md) "Implementation Order" for when it's worth doing (once a
third agent actually needs to be added, not speculatively now).

## `PipelineContext` (proposed shape, for when the split happens)

The connective tissue that lets each stage become a real, independently-testable agent
without every agent needing to know about every other agent's internals:

```
PipelineContext
  request: SearchRequest
  discovered_platforms: list[Platform]
  raw_listings: dict[platform_id, list[RawListing]]
  apartments: list[Apartment]
  ranked: list[RankedApartment]
  report_path: Path | None
  run_stats: dict            # execution_time_ms, per-platform timing, etc. — feeds Search Memory
```

Each agent would read the fields it needs off `PipelineContext` and write the fields it
produces, rather than being called with a long, growing parameter list. Not built now —
`RentalResearchAgent.run()`'s local variables already play this role informally; this is
what they'd become if/when the agents split apart for real.

## Notification Agent (genuinely unscoped)

Unlike the other five, Notification has no existing code shape to point to and no schema
reserved for it — there's no `notifications` table in [03_Data_Model.md](03_Data_Model.md)
because there's nothing concrete yet to design (send an email? a webhook? on what
trigger — every completed search, or only ones with `new_apartment_count > 0`?). Left
genuinely open rather than speculatively schema'd, per the same "don't design for
hypothetical requirements" principle — add it when a real notification requirement shows
up, not before.

## Related

- [01_System_Architecture.md](01_System_Architecture.md) — the pipeline these agents implement stages of
- [16_Knowledge_Engine.md](16_Knowledge_Engine.md) — the Learning Agent's actual design
