"""Where every installed analyzer is known — see docs/19_Analysis_Engine.md "Plugin
System". An analyzer self-registers by decorating its class with `@register_analyzer`;
adding a new analyzer never requires modifying `AnalysisEngine`/`AnalysisPipeline`.

Simpler than `src.connectors.sdk.ConnectorRegistry` (v2.0 Step 5) on purpose: connectors
are lazily imported per-platform, on demand, because which connector a given search
needs isn't known until `ConnectorFactory.get(platform)` is called. Analyzers have no
such per-apartment variability — every registered analyzer runs for every apartment —
so `src/analysis/analyzers/__init__.py` eagerly imports every analyzer module once, at
package-import time, and that's the only "loading" this registry ever needs.
"""

from __future__ import annotations


class AnalysisRegistry:
    _analyzers: dict[str, type] = {}

    @classmethod
    def register(cls, analyzer_class: type) -> type:
        """Applied as `@register_analyzer` directly under an analyzer class
        definition — runs at import time.
        """
        analyzer_name = getattr(analyzer_class, "analyzer_name", None)
        if not analyzer_name:
            raise ValueError(
                f"{analyzer_class.__name__} must set a class-level `analyzer_name` "
                "before it can be registered"
            )
        cls._analyzers[analyzer_name] = analyzer_class
        return analyzer_class

    @classmethod
    def get(cls, analyzer_name: str) -> type:
        try:
            return cls._analyzers[analyzer_name]
        except KeyError:
            raise KeyError(f"No analyzer registered for {analyzer_name!r}") from None

    @classmethod
    def is_registered(cls, analyzer_name: str) -> bool:
        return analyzer_name in cls._analyzers

    @classmethod
    def all(cls) -> list[type]:
        """Every analyzer class registered so far. Importing `src.analysis.analyzers`
        (done once, by `AnalysisPipeline`/`AnalysisEngine` at module load) guarantees
        every built-in analyzer has already run its `@register_analyzer` decorator by
        the time anything calls this.
        """
        return list(cls._analyzers.values())


def register_analyzer(analyzer_class: type) -> type:
    """Decorator form of `AnalysisRegistry.register` — put `@register_analyzer`
    directly above a `BaseAnalyzer` subclass.
    """
    return AnalysisRegistry.register(analyzer_class)
