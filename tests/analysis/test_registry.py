"""Unit tests for src/analysis/registry.py — AnalysisRegistry + register_analyzer."""

import unittest

from src.analysis.base_analyzer import BaseAnalyzer
from src.analysis.models import AnalyzerMetadata
from src.analysis.registry import AnalysisRegistry, register_analyzer


class _FakeAnalyzer(BaseAnalyzer):
    analyzer_name = "test_registry_fake_analyzer"

    def metadata(self) -> AnalyzerMetadata:
        return AnalyzerMetadata(analyzer_name=self.analyzer_name, version="1.0.0", category="test", description="fake")

    def analyze(self, apartment, context):
        raise NotImplementedError


class AnalysisRegistryTests(unittest.TestCase):
    def tearDown(self) -> None:
        AnalysisRegistry._analyzers.pop("test_registry_fake_analyzer", None)

    def test_register_analyzer_decorator_registers_the_class(self) -> None:
        register_analyzer(_FakeAnalyzer)
        self.assertTrue(AnalysisRegistry.is_registered("test_registry_fake_analyzer"))
        self.assertIs(AnalysisRegistry.get("test_registry_fake_analyzer"), _FakeAnalyzer)

    def test_register_requires_an_analyzer_name(self) -> None:
        class _NoName(BaseAnalyzer):
            def metadata(self):
                raise NotImplementedError

            def analyze(self, apartment, context):
                raise NotImplementedError

        with self.assertRaises(ValueError):
            AnalysisRegistry.register(_NoName)

    def test_get_raises_for_unknown_analyzer(self) -> None:
        with self.assertRaises(KeyError):
            AnalysisRegistry.get("no_such_analyzer_anywhere")

    def test_is_registered_is_false_for_unknown(self) -> None:
        self.assertFalse(AnalysisRegistry.is_registered("something_never_registered"))

    def test_all_eleven_built_in_analyzers_are_registered_by_importing_the_package(self) -> None:
        import src.analysis.analyzers  # noqa: F401 - import triggers registration

        expected = {
            "walking_distance", "public_transport", "nearby_supermarkets", "nearby_pharmacies",
            "nearby_hospitals", "nearby_universities", "nearby_schools", "nearby_parks",
            "nearby_restaurants", "nearby_gyms", "nearby_parking",
        }
        registered = {cls.analyzer_name for cls in AnalysisRegistry.all()}
        self.assertTrue(expected.issubset(registered))


if __name__ == "__main__":
    unittest.main()
