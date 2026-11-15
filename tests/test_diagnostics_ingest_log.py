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

    def test_orchestrator_failure_lines_are_ingested_as_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "build.log"
            output = root / "report.json"
            source.write_text(
                "scons: *** [target] Error 1\n"
                "make[2]: *** [other] Error 2\n"
                "ninja: build stopped: subcommand failed.\\n",
                encoding="utf-8",
            )
            report = ingest_log(source, output, "build_log", "test")
            self.assertEqual(report["candidate_count"], 3)
            self.assertEqual(report["classification"]["severity_counts"]["error"], 3)
            self.assertEqual(report["health_status"], "degraded")
            self.assertTrue(all(event["source"] == "build_orchestrator" for event in report["classification"]["events"]))

    def test_gettext_fallback_is_a_warning_not_an_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "build.log"
            output = root / "report.json"
            source.write_text("msgfmt not found, using .po files instead of .mo\n", encoding="utf-8")
            report = ingest_log(source, output, "build_log", "test")
            self.assertEqual(report["classification"]["severity_counts"]["warning"], 1)
            self.assertEqual(report["health_status"], "warnings")

    def test_warning_and_unknown_are_both_visible_in_health_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "build.log"
            output = root / "report.json"
            source.write_text("compiler.cpp: warning: fallback used\nunsupported configuration detail\n", encoding="utf-8")
            report = ingest_log(source, output, "build_log", "test")
            self.assertEqual(report["health_status"], "warnings_and_unclassified")
            self.assertEqual(report["classification"]["unknown_events"], 1)

    def test_missing_log_is_reported_without_fabricating_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = ingest_log(root / "missing.log", root / "report.json", "build_log", "test")
            self.assertEqual(report["health_status"], "missing_log")
            self.assertEqual(report["candidate_count"], 0)


if __name__ == "__main__":
    unittest.main()
