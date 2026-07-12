import os
from pathlib import Path


def build_status_message(api_key: str | None) -> str:
    """Return a simple status message for the rental agent setup."""
    if api_key:
        return "Rental agent is ready to use OpenAI integration."

    return "Rental agent is not configured yet. Set OPENAI_API_KEY in your environment or .env file."


def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY") or None
    print(build_status_message(api_key))


if __name__ == "__main__":
    main()
