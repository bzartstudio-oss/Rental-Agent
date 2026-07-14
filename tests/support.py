"""Shared test support (not a test module itself — no `test_` prefix, so
`unittest discover` skips it).

`image_collector.collect_image` and `raw_page_store.save_page` both default to writing
into real project `data/` (see their `base_dir` parameters). Any test that runs a real
connector or the real pipeline through demo_platform needs those redirected to a temp
directory, or it silently writes real files into real project data on every test run —
this happened for a while before being caught (see learning/architecture_notes.md
2026-07-14 "test-isolation gap").
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.collectors import image_collector, raw_page_store


@contextmanager
def isolated_collectors(tmp_dir: Path) -> Iterator[None]:
    media_dir = tmp_dir / "media"
    raw_pages_dir = tmp_dir / "raw_pages"

    original_collect_image = image_collector.collect_image
    original_save_page = raw_page_store.save_page

    image_collector.collect_image = (
        lambda apartment_id, url, filename: original_collect_image(
            apartment_id, url, filename, base_dir=media_dir
        )
    )
    raw_page_store.save_page = (
        lambda platform_id, content, suffix="html": original_save_page(
            platform_id, content, suffix, base_dir=raw_pages_dir
        )
    )

    try:
        yield
    finally:
        image_collector.collect_image = original_collect_image
        raw_page_store.save_page = original_save_page
