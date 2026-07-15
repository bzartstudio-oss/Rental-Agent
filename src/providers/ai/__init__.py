"""Eagerly imports every built-in AI provider so its `register_provider(...)` call
runs — same convention as `providers.data`.
"""

from __future__ import annotations

from src.providers.ai import null_ai_provider as _null_ai_provider  # noqa: F401
from src.providers.ai import ollama_ai_provider as _ollama_ai_provider  # noqa: F401
