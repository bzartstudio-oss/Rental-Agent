import unittest

from src.rental_agent import build_status_message


class RentalAgentTests(unittest.TestCase):
    def test_returns_ready_message_when_api_key_present(self):
        message = build_status_message("test-key")
        self.assertIn("ready", message.lower())
        self.assertIn("openai", message.lower())

    def test_returns_setup_hint_when_api_key_missing(self):
        message = build_status_message(None)
        self.assertIn("set", message.lower())
        self.assertIn("openai_api_key", message.lower())


if __name__ == "__main__":
    unittest.main()
