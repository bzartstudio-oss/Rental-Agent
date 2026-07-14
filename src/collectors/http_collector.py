"""Plain HTTP fetching, for platforms with a usable API rather than needing browser
automation — see docs/06_Connector_Framework.md. A connector uses this instead of
browser_collector.py when the target doesn't need JS rendering.
"""

from __future__ import annotations

import requests


def fetch_text(url: str, timeout: int = 30, **kwargs) -> str:
    response = requests.get(url, timeout=timeout, **kwargs)
    response.raise_for_status()
    return response.text


def fetch_json(url: str, timeout: int = 30, **kwargs) -> dict:
    response = requests.get(url, timeout=timeout, **kwargs)
    response.raise_for_status()
    return response.json()
