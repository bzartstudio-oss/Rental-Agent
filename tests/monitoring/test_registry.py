"""`MonitoringRegistry` self-registration tests — mirrors
`tests/discovery/automatic/test_registry.py`'s own shape. Proves "adding a new
event type/detector requires no `MonitoringEngine` changes" (the mission's own
words): a brand-new, test-only detector registers and is immediately picked up
by `MonitoringRegistry.all()`, which is exactly what `MonitoringEngine._execute()`
iterates.
"""

from __future__ import annotations

import unittest

from src.monitoring.base_detector import EventDetector, MonitoringDetectionContext
from src.monitoring.exceptions import MonitoringConfigurationError
from src.monitoring.metadata import EventDetectorMetadata
from src.monitoring.models import MonitoringEvent
from src.monitoring.registry import MonitoringRegistry, register_event_detector


class _FakeDetector(EventDetector):
    detector_id = "fake_test_detector"

    def metadata(self) -> EventDetectorMetadata:
        return EventDetectorMetadata(detector_id=self.detector_id, display_name="Fake", description="Test-only.")

    def detect(self, context: MonitoringDetectionContext) -> list[MonitoringEvent]:
        return []


class MonitoringRegistryTests(unittest.TestCase):
    def tearDown(self) -> None:
        MonitoringRegistry._detectors.pop("fake_test_detector", None)

    def test_built_in_detectors_are_all_registered(self) -> None:
        registered_ids = {d.detector_id for d in MonitoringRegistry.all()}
        for expected in ("apartment_change", "ranking_change", "filter_match", "platform_health", "discovery"):
            self.assertIn(expected, registered_ids)

    def test_adding_a_new_detector_requires_no_registry_or_engine_changes(self) -> None:
        before = len(MonitoringRegistry.all())
        register_event_detector(_FakeDetector())
        after = MonitoringRegistry.all()
        self.assertEqual(len(after), before + 1)
        self.assertIn("fake_test_detector", {d.detector_id for d in after})

    def test_get_unknown_detector_raises_configuration_error(self) -> None:
        with self.assertRaises(MonitoringConfigurationError):
            MonitoringRegistry.get("does_not_exist")

    def test_register_rejects_a_non_detector_instance(self) -> None:
        with self.assertRaises(MonitoringConfigurationError):
            register_event_detector(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
