"""Downloads listing images and saves them under data/media/ — see docs/06_Connector_Framework.md
"Image Extraction". `download_image` uses `urllib` (stdlib) rather than `requests` so it
handles both real http(s):// URLs and file:// URLs uniformly — fixture-based connectors
(see connectors/demo_platform.py) use local file:// image paths, and the Analysis Engine
that calls this shouldn't need to know or care which kind of URL a given connector produces.
"""

from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen

from src.core.config import DATA_DIR

MEDIA_DIR = DATA_DIR / "media"


def download_image(url: str) -> bytes:
    """Fetch raw image bytes from `url`. The only networked (or local-file-reading, for
    file:// URLs) step here — kept separate from save_image() so the file-writing logic
    can be unit-tested without depending on a live fetch.
    """
    with urlopen(url) as response:
        return response.read()


def save_image(apartment_id: str, image_bytes: bytes, filename: str, base_dir: Path = MEDIA_DIR) -> Path:
    """Write `image_bytes` under <base_dir>/<apartment_id>/<filename>. Pure file I/O, no
    network — this is what tests exercise directly, and `base_dir` is overridable so tests
    don't write into real project data.
    """
    apartment_dir = base_dir / apartment_id
    apartment_dir.mkdir(parents=True, exist_ok=True)
    path = apartment_dir / filename
    path.write_bytes(image_bytes)
    return path


def collect_image(apartment_id: str, url: str, filename: str, base_dir: Path = MEDIA_DIR) -> Path:
    """Convenience wrapper combining the two steps above — what a real caller uses."""
    return save_image(apartment_id, download_image(url), filename, base_dir=base_dir)
