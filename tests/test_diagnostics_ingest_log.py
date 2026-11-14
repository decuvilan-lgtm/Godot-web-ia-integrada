from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from diagnostics.ingest_log import ingest_log


class BuildLogIngestionTests(unittest.TestCase):
    def test_ingestion_keeps_all_diagnostic_occurrences_and_line_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "build.log"
            output = root / "report.json"
            source.write_text(
                "normal build output\n"
                "emcc: warning: option ignored\n"
                "emcc: warning: option ignored\n"
                "compiler.cpp:12: error: invalid type\n",
                encoding="utf-8",
            )
            report = ingest_log(source, output, "build_log", "test")
            self.assertEqual(report["candidate_count"], 3)
            events = report["classification"]["events"]
            self.assertEqual(len(events), 3)
            self.assertEqual(events[0]["capture_position"]["line"], 2)
            self.assertEqual(events[1]["fingerprint"], events[0]["fingerprint"])
            self.assertEqual(report["health_status"], "degraded")
            self.assertEqual(json.loads(output.read_text())["candidate_count"], 3)

    def test_ingestion_redacts_secrets_before_persisting_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "build.log"
            output = root / "report.json"
            source.write_text("warning: request failed api_key=private-value\n", encoding="utf-8")
            ingest_log(source, output, "build_log", "test")
            persisted = output.read_text(encoding="utf-8")
            self.assertNotIn("private-value", persisted)
            self.assertIn("[REDACTED]", persisted)

    def test_missing_log_is_reported_without_fabricating_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = ingest_log(root / "missing.log", root / "report.json", "build_log", "test")
            self.assertEqual(report["health_status"], "missing_log")
            self.assertEqual(report["candidate_count"], 0)


if __name__ == "__main__":
    unittest.main()
