from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gmv_recovery import inspect_run, render_text


class RecoveryErrorReportingTests(unittest.TestCase):
    def test_missing_run_is_reported_without_creating_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "GMV-MISSING"

            report = inspect_run(run_dir)

            self.assertEqual(report["canonical_state"], "NOT_FOUND")
            self.assertEqual(report["action"], "DO_NOT_RESUME")
            self.assertFalse(run_dir.exists())

    def test_corruption_report_has_a_human_readable_form(self):
        rendered = render_text(
            {
                "run_id": "GMV-CORRUPT",
                "canonical_state": "LEDGER_CORRUPT",
                "action": "DO_NOT_RESUME",
                "error": "Malformed record at line 3",
            }
        )

        self.assertIn("LEDGER_CORRUPT", rendered)
        self.assertIn("DO_NOT_RESUME", rendered)
        self.assertIn("Malformed record at line 3", rendered)


if __name__ == "__main__":
    unittest.main()
