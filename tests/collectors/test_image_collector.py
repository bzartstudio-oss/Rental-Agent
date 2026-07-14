import tempfile
import unittest
from pathlib import Path

from src.collectors import image_collector


class ImageCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self._tmp_dir.name)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_save_image_writes_bytes_and_returns_path(self) -> None:
        path = image_collector.save_image("apt-1", b"fake-image-bytes", "photo1.jpg", base_dir=self.base_dir)

        self.assertTrue(path.exists())
        self.assertEqual(path.read_bytes(), b"fake-image-bytes")
        self.assertEqual(path.parent.name, "apt-1")

    def test_download_image_reads_a_local_file_url(self) -> None:
        """`download_image` must handle file:// URLs the same way it handles http(s)://
        ones, since fixture-based connectors (demo_platform.py) use local image files —
        this proves that without depending on network access in the test.
        """
        source_path = self.base_dir / "source.png"
        source_path.write_bytes(b"\x89PNG\r\n\x1a\nfake-png-data")

        content = image_collector.download_image(source_path.as_uri())

        self.assertEqual(content, b"\x89PNG\r\n\x1a\nfake-png-data")

    def test_collect_image_downloads_and_saves_in_one_step(self) -> None:
        source_path = self.base_dir / "source.png"
        source_path.write_bytes(b"pretend-png-bytes")

        saved_path = image_collector.collect_image(
            "apt-2", source_path.as_uri(), "photo1.png", base_dir=self.base_dir
        )

        self.assertTrue(saved_path.exists())
        self.assertEqual(saved_path.read_bytes(), b"pretend-png-bytes")


if __name__ == "__main__":
    unittest.main()
