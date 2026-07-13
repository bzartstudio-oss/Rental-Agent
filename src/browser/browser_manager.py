from playwright.sync_api import sync_playwright


def test_browser():

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page()

        page.goto("https://example.com")

        page.wait_for_timeout(5000)

        browser.close()