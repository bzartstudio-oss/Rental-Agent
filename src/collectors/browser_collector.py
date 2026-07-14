"""Generic, platform-agnostic page fetching via Playwright/Chromium.

Promotes the original src/browser/browser_manager.py (a one-off test function that just
opened example.com and closed again) into a reusable class, per the Connector/Collector
split in docs/06_Connector_Framework.md: a connector must contain only platform-specific
parsing logic, never its own browser-launching code — this is the shared fetch
infrastructure every connector calls into instead.
"""

from __future__ import annotations

from playwright.sync_api import Browser, Page, sync_playwright


class BrowserCollector:
    """Use as a context manager so one browser instance is reused across every fetch in
    a connector's run, instead of paying Playwright's launch cost per page:

        with BrowserCollector() as browser:
            html = browser.fetch("https://example.com")

    `headless` defaults to True (production behaviour) — the original browser_manager.py
    hardcoded `headless=False`, which was fine for a manual one-off test but would slow
    down every real search run; pass `headless=False` explicitly when debugging a connector.
    """

    def __init__(self, headless: bool = True, timeout_ms: int = 30_000) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser: Browser | None = None

    def __enter__(self) -> "BrowserCollector":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def fetch(self, url: str, wait_ms: int = 0) -> str:
        """Load `url` and return the rendered page's HTML.

        `wait_ms` is an escape hatch for pages whose content is still loading after
        Playwright's own navigation-complete signal (e.g. content that streams in after
        an XHR) — most connectors shouldn't need it.
        """
        if self._browser is None:
            raise RuntimeError(
                "BrowserCollector must be used as a context manager: "
                "'with BrowserCollector() as browser: ...'"
            )

        page: Page = self._browser.new_page()
        try:
            page.goto(url, timeout=self.timeout_ms)
            if wait_ms:
                page.wait_for_timeout(wait_ms)
            return page.content()
        finally:
            page.close()
