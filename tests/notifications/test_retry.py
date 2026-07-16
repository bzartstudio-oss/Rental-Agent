"""`retry.is_retryable()`/`should_dead_letter()`/`compute_next_attempt_at()` —
configurable backoff/dead-letter policy in isolation (idempotency of the
retry workflow itself is covered end-to-end in `test_engine.py`).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.notifications import retry
from src.notifications.models import NotificationPolicy

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


class RetryPolicyTests(unittest.TestCase):
    def test_non_retryable_categories_are_never_retryable(self) -> None:
        policy = NotificationPolicy()
        for category in policy.non_retryable_error_categories:
            self.assertFalse(retry.is_retryable(category, policy))

    def test_known_retryable_categories_are_retryable(self) -> None:
        policy = NotificationPolicy()
        for category in policy.retryable_error_categories:
            self.assertTrue(retry.is_retryable(category, policy))

    def test_unknown_category_defaults_to_retryable(self) -> None:
        policy = NotificationPolicy()
        self.assertTrue(retry.is_retryable("some_never_seen_category", policy))

    def test_none_category_defaults_to_retryable(self) -> None:
        policy = NotificationPolicy()
        self.assertTrue(retry.is_retryable(None, policy))

    def test_dead_letter_triggers_once_attempts_reach_the_configured_threshold(self) -> None:
        policy = NotificationPolicy(dead_letter_after_attempts=5)
        self.assertFalse(retry.should_dead_letter(4, policy))
        self.assertTrue(retry.should_dead_letter(5, policy))
        self.assertTrue(retry.should_dead_letter(6, policy))

    def test_backoff_grows_exponentially_with_attempt_count(self) -> None:
        policy = NotificationPolicy(retry_backoff_base_seconds=30.0, retry_backoff_max_seconds=3600.0)
        first = retry.compute_next_attempt_at(1, policy, _NOW)
        second = retry.compute_next_attempt_at(2, policy, _NOW)
        third = retry.compute_next_attempt_at(3, policy, _NOW)
        self.assertEqual((first - _NOW).total_seconds(), 30.0)
        self.assertEqual((second - _NOW).total_seconds(), 60.0)
        self.assertEqual((third - _NOW).total_seconds(), 120.0)

    def test_backoff_is_capped_at_the_configured_maximum(self) -> None:
        policy = NotificationPolicy(retry_backoff_base_seconds=30.0, retry_backoff_max_seconds=100.0)
        next_attempt = retry.compute_next_attempt_at(10, policy, _NOW)
        self.assertEqual((next_attempt - _NOW).total_seconds(), 100.0)


if __name__ == "__main__":
    unittest.main()
