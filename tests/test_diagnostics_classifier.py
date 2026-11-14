from __future__ import annotations

import unittest

from diagnostics.classifier import classify_event, summarize_events


class DiagnosticsClassifierTests(unittest.TestCase):
    def test_godot_warning_is_not_promoted_by_chromium_console_error(self):
        event = classify_event(
            "WARNING: HTTPS proxy feature is not available",
            transport_type="error",
            source_hint="browser_console",
        )
        self.assertEqual(event["source"], "godot")
        self.assertEqual(event["declared_severity"], "warning")
        self.assertEqual(event["transport_type"], "error")

    def test_godot_error_remains_error(self):
        event = classify_event(
            "ERROR: Attempt of waiting to finish on a thread that was never started.",
            transport_type="error",
        )
        self.assertEqual(event["source"], "godot")
        self.assertEqual(event["declared_severity"], "error")
        self.assertEqual(event["category"], "threads")

    def test_compiler_warning_and_error_are_distinguished(self):
        warning = classify_event("foo.cpp:12: warning: unused variable", source_hint="compiler")
        error = classify_event("foo.cpp:13: error: unknown type", source_hint="compiler")
        self.assertEqual(warning["declared_severity"], "warning")
        self.assertEqual(error["declared_severity"], "error")

    def test_unknown_is_preserved_not_silenced(self):
        raw = "A future tool emitted a message we do not recognize"
        event = classify_event(raw)
        self.assertEqual(event["original_message"], raw)
        self.assertEqual(event["classification_status"], "unknown")
        self.assertEqual(event["declared_severity"], "unknown")

    def test_transport_and_source_severity_are_independent(self):
        event = classify_event("WARNING: something", transport_type="error")
        self.assertNotEqual(event["transport_type"], event["declared_severity"])

    def test_same_text_from_different_sources_does_not_merge(self):
        a = classify_event("connection failed", source_hint="node", transport_type="error")
        b = classify_event("connection failed", source_hint="javascript", transport_type="error")
        self.assertNotEqual(a["fingerprint"], b["fingerprint"])

    def test_duplicate_summary_keeps_all_occurrences(self):
        events = [classify_event("WARNING: repeated", transport_type="error") for _ in range(3)]
        report = summarize_events(events)
        self.assertEqual(report["total_events"], 3)
        self.assertEqual(report["duplicate_occurrences"], 2)
        self.assertEqual(len(report["events"]), 3)

    def test_browser_log_is_notice_not_unknown(self):
        event = classify_event("Editor initialized", transport_type="log", source_hint="browser_console")
        self.assertEqual(event["declared_severity"], "notice")
        self.assertEqual(event["classification_status"], "classified")

    def test_request_failures_are_network_events(self):
        event = classify_event("GET https://example.invalid: net::ERR_FAILED", transport_type="error", source_hint="network")
        self.assertEqual(event["category"], "network")
        self.assertEqual(event["declared_severity"], "error")

    def test_severity_basis_explains_why_a_level_was_assigned(self):
        engine = classify_event("WARNING: expected fallback", transport_type="error")
        browser = classify_event("uncaught exception", transport_type="error", source_hint="javascript")
        self.assertEqual(engine["severity_basis"], "exact_prefix")
        self.assertEqual(browser["severity_basis"], "transport_fallback")

    def test_different_locations_do_not_share_a_fingerprint(self):
        first = classify_event("ERROR: operation failed", location={"url": "engine.cpp", "lineNumber": 10})
        second = classify_event("ERROR: operation failed", location={"url": "engine.cpp", "lineNumber": 20})
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_category_does_not_claim_root_cause(self):
        event = classify_event("ERROR: TCPServer listen failed")
        self.assertEqual(event["category"], "network")
        self.assertNotIn("root_cause", event)


if __name__ == "__main__":
    unittest.main()
