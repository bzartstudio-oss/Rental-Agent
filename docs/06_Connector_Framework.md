# 06 — Connector Framework

Status: V1.0 Connector/Collector split live in code. **v2.0 Connector SDK designed
2026-07-14, not yet implemented** — see "Connector SDK" below.

## Why a Connector Framework

Every rental platform exposes listings differently — some have a public API, most don't and need browser automation. A connector framework means the rest of the pipeline (Analysis Engine, Ranking, Reports) never needs to know which platform a listing came from — it only ever talks to the shared `RawListing`/`Apartment` shapes in [03_Data_Model.md](03_Data_Model.md). This module is where Principle 7 ("business logic must remain independent from any individual website") is enforced — see the guardrail in [01_System_Architecture.md](01_System_Architecture.md).

## Two Layers: Connectors vs. Collectors

V1.0 splits what earlier drafts called "connectors" into two distinct concerns, because otherwise every connector reimplements its own browser-launching and image-downloading code:

- **Connector** (`connectors/<platform_id>.py`) — platform-specific *only*: knows this one site's URL structure, page layout/selectors or API shape, and how to turn `SearchRequest` criteria into that platform's query. Contains zero fetch/browser mechanics of its own.
- **Collector** (`collectors/`) — generic, reusable, platform-agnostic infrastructure that connectors call into:
  - `browser_collector.py` — Playwright/Chromium page fetching (absorbs the existing `src/browser/browser_manager.py`, expanded into a reusable class rather than a one-off test function)
  - `http_collector.py` — plain HTTP requests, for platforms with a usable API
  - `image_collector.py` — downloads listing images to `data/media/`, returns paths for `apartment_images` rows
  - `raw_page_store.py` — persists raw HTML/screenshots to `data/raw_pages/`, returns paths for `raw_captures` rows

A connector calls a collector; a collector never calls a connector. This keeps the reusable fetch/persistence machinery in one place while keeping platform knowledge fully isolated.

## Connector Contract

`connectors/base.py` defines the interface every connector implements:

- `platform_id: str` — matches this connector's row in the `platforms` table
- `search(criteria: SearchCriteria) -> list[RawListing]` — given normalized criteria derived from a `SearchRequest`, return raw results. Internally, this method uses a Collector to fetch pages/data and parses platform-specific structure into `RawListing` objects — it does not return platform-native shapes.

`RawListing` is intentionally looser than `Apartment` (it's pre-normalization) but still a shared shape across all connectors, so the Analysis Engine ([07_Analysis_Engine.md](07_Analysis_Engine.md)) has one input contract regardless of platform.

## Image Extraction (Principle: "image extraction")

A connector's `search()` includes image URLs in each `RawListing`. It is the Analysis Engine, not the connector, that decides to call `image_collector.py` to actually download them (see [07_Analysis_Engine.md](07_Analysis_Engine.md)) — this keeps the connector's job strictly to "get data off this website," not "manage local file storage."

## Adding a New Connector

1. Create `src/connectors/<platform_id>.py` implementing the contract in `base.py`
2. Use `collectors/browser_collector.py` or `http_collector.py` for actual fetching — don't hand-roll fetch logic in the connector
3. Register the platform in `discovery/platform_registry.py` (see [05_Platform_Discovery.md](05_Platform_Discovery.md))
4. Add a test in `tests/connectors/test_<platform_id>.py`
5. Log platform-specific findings (rate limits, auth, page structure) in [../notes/Research.md](../notes/Research.md) first, then durable lessons in [../learning/playwright_notes.md](../learning/playwright_notes.md) or a new topic file if warranted

## Existing Connectors (2026-07-14)

- **`demo_platform.py`** and **`demo_platform_two.py`** — real connectors (real Playwright fetch, real BeautifulSoup parsing) against local HTML fixtures, not live commercial sites. Built to prove the whole framework end-to-end while the actual first platform target was still an open product decision — see [10_Roadmap.md](10_Roadmap.md) "Reference Connector Strategy". Not real rental platforms; each module's own docstring says so.

No real-platform connector exists yet. Adding one is the next real piece of work, following the same steps below.

## Error Handling & Rate Limiting

Every connector must fail gracefully — a broken platform must not crash the whole `RentalResearchAgent` run. **Resolved (2026-07-14):** `core/agent.py` catches any exception from a connector's `search()` call and skips that platform, continuing with whatever other platforms returned — see the next section, which used to be an open question here.

*Still TBD: exact retry/backoff policy* — respect reasonable rate limits / robots.txt for scraped sites regardless.

## Resolved: Connector Failure Handling

Continue with partial results rather than aborting the whole `SearchRequest` — Principle 1 ("never lose information") argues against discarding whatever platforms *did* succeed. Proven in `tests/core/test_agent.py::test_a_broken_connector_does_not_crash_the_whole_run`, which registers a platform pointing at a nonexistent connector module alongside a working one and confirms the working platform's results still come through.

## Connector SDK (v2.0, designed — not yet implemented)

**Problem this solves:** `demo_platform.py` and `demo_platform_two.py` (v1.1) each
independently implement the same three-step sequence — fetch via `BrowserCollector`,
save the raw page via `raw_page_store`, then parse. That's not platform-specific logic;
it's boilerplate duplicated once per connector, which is exactly what "a new connector
should require minimal code" says shouldn't happen once there are more than two.

**Design: `BaseConnector` as a template method.** `connectors/base.py` grows from a bare
`ABC` with one abstract method into a class that implements `search()` itself, calling
out to smaller hooks that subclasses provide:

```
class BaseConnector(ABC):
    platform_id: str

    def search(self, criteria: dict) -> list[RawListing]:
        # Implemented ONCE, here — not per connector:
        url = self.build_url(criteria)
        html = self.fetch(url)
        raw_page_store.save_page(self.platform_id, html)   # every connector gets this for free
        return self.parse(html)

    def fetch(self, url: str) -> str:
        # Default: BrowserCollector. A connector for a platform with a real API
        # overrides this to use http_collector instead — one method, not a
        # parallel class hierarchy.
        with BrowserCollector() as browser:
            return browser.fetch(url)

    @abstractmethod
    def build_url(self, criteria: dict) -> str: ...   # the ONE genuinely platform-specific thing

    @abstractmethod
    def parse(self, html: str) -> list[RawListing]: ...  # the OTHER genuinely platform-specific thing
```

A new connector subclass implements exactly two methods (`build_url`, `parse`) — fetching
and raw-page persistence are inherited, not rewritten. `demo_platform.py`/
`demo_platform_two.py` migrate to this base with no behavior change (their `build_url`
becomes "return the fixture's `file://` URI, ignore criteria" — unchanged from what they
do today, just relocated out of `search()`).

**Extraction helpers.** `base.py` also gains small static helpers used by every `parse()`
implementation today via repeated BeautifulSoup calls — `_text(element, selector)`,
`_number(element, selector)`, `_attr(element, selector, attribute)` — each wrapping the
"find element, get text/attribute, handle missing gracefully" pattern currently
duplicated across both demo connectors' `_parse()` methods.

**What stays exactly the same:** the `Connector` name is kept as an alias for
`BaseConnector` (or `BaseConnector` replaces it directly — an implementation-time
choice, not an architecture one) so `core/agent.py`'s `CONNECTOR = <Subclass>` /
`isinstance` expectations don't change. The Collector layer (`browser_collector.py`,
`http_collector.py`, `image_collector.py`, `raw_page_store.py`) is unchanged — the SDK
calls the same collectors, just from inside `BaseConnector` instead of from each
connector module.

## Image Management (v2.0, designed — not yet implemented)

A connector's role is unchanged: report each listing's image URLs in `RawListing.image_urls`,
same as v1.0/v1.1. What's new lives downstream, in the Analysis Engine, not here — see
[07_Analysis_Engine.md](07_Analysis_Engine.md) "Image Change Detection" for how the
system now notices when a re-observed apartment's image set has changed (new photos
added, old ones removed) instead of only handling images at first-discovery time.
