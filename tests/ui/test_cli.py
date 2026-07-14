"""Phase 5 exit-criteria test (docs/10_Roadmap.md): running the CLI end-to-end produces
a real output/<search_id>.html with real data, images, URLs, and score breakdowns.
"""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from src.storage.database import Database
from src.ui import cli
from tests.support import isolated_collectors


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmp_dir.name) / "test.db")
        self.output_dir = Path(self._tmp_dir.name) / "output"
        self._collectors_cm = isolated_collectors(Path(self._tmp_dir.name))
        self._collectors_cm.__enter__()

    def tearDown(self) -> None:
        self._collectors_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()

    def test_cli_run_produces_a_real_report(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = cli.main(
                ["--location", "Example City", "--max-price", "2000"],
                db=self.db,
                output_dir=self.output_dir,
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("Report:", stdout.getvalue())

        report_files = list(self.output_dir.glob("*.html"))
        self.assertEqual(len(report_files), 1)

        content = report_files[0].read_text(encoding="utf-8")
        self.assertIn("Rental Search Report", content)
        self.assertIn("$", content)  # price shown
        self.assertIn("Original listing", content)  # original listing URL present
        self.assertIn("Score:", content)  # score breakdown present

    def test_cli_auto_registers_known_platforms_idempotently(self) -> None:
        # Running twice must not raise (e.g. from a duplicate-registration IntegrityError)
        cli.main(["--location", "Example City"], db=self.db, output_dir=self.output_dir)
        exit_code = cli.main(["--location", "Example City"], db=self.db, output_dir=self.output_dir)

        self.assertEqual(exit_code, 0)

    def test_cli_requires_location(self) -> None:
        with self.assertRaises(SystemExit):
            cli.main([], db=self.db, output_dir=self.output_dir)


if __name__ == "__main__":
    unittest.main()
