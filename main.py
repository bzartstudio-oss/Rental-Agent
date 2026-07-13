from src.config.config_loader import load_settings
from src.browser.browser_manager import test_browser


def main():
    settings = load_settings()

    print("Rental Intelligence Agent")
    print("--------------------------")
    print(settings.search.city)

    try:
        test_browser()
    finally:
        print("Browser session completed.")


if __name__ == "__main__":
    main()