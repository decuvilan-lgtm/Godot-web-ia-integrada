from __future__ import annotations

import unittest

from diagnostics.classifier import classify_event, link_continuation_events, redact_sensitive_payload, summarize_events


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

    def test_godot_script_error_has_project_script_classification(self):
        event = classify_event(
            "SCRIPT ERROR: Parse Error: Identifier not declared",
            transport_type="error",
            context="godot_project_runtime",
        )
        self.assertEqual(event["source"], "godot_script")
        self.assertEqual(event["declared_severity"], "error")
        self.assertEqual(event["category"], "scripts")
        self.assertEqual(event["classification_rule"], "godot.script_error")
        self.assertEqual(event["context"], "godot_project_runtime")

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

    def test_fatal_messages_have_distinct_severity(self):
        godot = classify_event("FATAL: unrecoverable engine failure")
        compiler = classify_event("compiler: fatal error: invalid state")
        self.assertEqual(godot["declared_severity"], "fatal")
        self.assertEqual(compiler["declared_severity"], "fatal")

    def test_rule_identifier_explains_classification(self):
        event = classify_event("WARNING: unsupported feature", transport_type="error")
        self.assertEqual(event["classification_rule"], "godot.prefix.warning")

    def test_secrets_and_url_queries_are_redacted_before_reporting(self):
        event = classify_event(
            "request failed https://example.invalid/path?access_token=abc123&state=xyz "
            "Authorization: Bearer secret-value api_key=key-123",
            transport_type="error",
            source_hint="javascript",
        )
        self.assertNotIn("abc123", event["original_message"])
        self.assertNotIn("secret-value", event["original_message"])
        self.assertNotIn("key-123", event["original_message"])
        self.assertIn("[REDACTED_QUERY]", event["original_message"])
        self.assertGreaterEqual(event["redactions_applied"], 3)

    def test_nested_report_payloads_are_redacted_recursively(self):
        payload = {
            "console_events": [{"text": "GET https://example.invalid/?token=secret"}],
            "runtime": {"resource_url": "https://example.invalid/app.js?api_key=private"},
        }
        safe, count = redact_sensitive_payload(payload)
        serialized = str(safe)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("private", serialized)
        self.assertEqual(count, 2)

    def test_godot_stack_trace_is_context_not_a_second_error(self):
        event = classify_event(
            "   at: wait_to_finish (core/os/thread.cpp:84)",
            transport_type="error",
            source_hint="browser_console",
        )
        self.assertEqual(event["event_role"], "continuation")
        self.assertEqual(event["declared_severity"], "notice")
        self.assertEqual(event["source"], "godot_stack_trace")
        self.assertEqual(event["category"], "diagnostic_context")

    def test_emscripten_main_thread_blocking_message_is_a_warning(self):
        event = classify_event(
            "Blocking on the main thread is very dangerous, see documentation",
            transport_type="error",
            source_hint="browser_console",
        )
        self.assertEqual(event["source"], "emscripten")
        self.assertEqual(event["declared_severity"], "warning")
        self.assertEqual(event["classification_rule"], "emscripten.blocking_main_thread.warning")

    def test_continuation_is_linked_to_nearest_root_without_inflating_errors(self):
        root = classify_event("ERROR: worker failed", timestamp="1000")
        frame = classify_event(
            "   at: wait_to_finish (core/os/thread.cpp:84)",
            transport_type="error",
            source_hint="browser_console",
            timestamp="1200",
        )
        linked = link_continuation_events([root, frame])
        report = summarize_events(linked)
        self.assertEqual(linked[1]["related_event_index"], 0)
        self.assertEqual(linked[1]["relation"], "stack_trace_for")
        self.assertEqual(report["severity_counts"]["error"], 1)

    def test_project_stack_frame_without_leading_whitespace_is_classified(self):
        root = classify_event(
            "ERROR: PROJECT_DIAG_FIXTURE: intentional runtime error",
            timestamp="1000",
            context="godot_project_runtime",
        )
        frame = classify_event(
            "at: _ready (res://main.gd:5)",
            source_hint="browser_console",
            timestamp="1200",
            context="godot_project_runtime",
        )
        self.assertEqual(frame["event_role"], "continuation")
        linked = link_continuation_events([root, frame])
        self.assertEqual(linked[1]["related_event_index"], 0)
        self.assertEqual(linked[0]["godot_source_locations"][0]["path"], "res://main.gd")
        self.assertEqual(linked[0]["godot_source_locations"][0]["line"], 5)

    def test_gdscript_backtrace_frame_is_correlated_to_root_error(self):
        root = classify_event(
            "ERROR: PROJECT_DIAG_FIXTURE: intentional runtime error",
            timestamp="1000",
            context="godot_project_runtime",
        )
        frame = classify_event(
            "       [0] _ready (res://main.gd:5)",
            source_hint="browser_console",
            transport_type="error",
            timestamp="1200",
            context="godot_project_runtime",
        )
        linked = link_continuation_events([root, frame])
        self.assertEqual(linked[1]["event_role"], "continuation")
        self.assertEqual(linked[1]["related_event_index"], 0)
        self.assertEqual(linked[0]["godot_source_locations"][0]["line"], 5)

    def test_print_stack_frame_format_is_classified_as_continuation(self):
        root = classify_event(
            "ERROR: PROJECT_DIAG_FIXTURE: intentional runtime error",
            timestamp="1000",
            context="godot_project_runtime",
        )
        frame = classify_event(
            "Frame 0 - res://main.gd:6 in function '_ready'",
            source_hint="browser_console",
            timestamp="1200",
            context="godot_project_runtime",
        )
        linked = link_continuation_events([root, frame])
        self.assertEqual(linked[1]["event_role"], "continuation")
        self.assertEqual(linked[1]["related_event_index"], 0)
        self.assertEqual(linked[0]["godot_source_locations"][0]["line"], 6)

    def test_project_stack_frame_adds_script_path_and_line_to_root(self):
        root = classify_event(
            "SCRIPT ERROR: Invalid call",
            timestamp="1000",
            context="godot_project_runtime",
        )
        frame = classify_event(
            "   at: _ready (res://scripts/player.gd:27)",
            source_hint="browser_console",
            timestamp="1200",
            context="godot_project_runtime",
        )
        linked = link_continuation_events([root, frame])
        self.assertEqual(linked[1]["related_event_index"], 0)
        self.assertEqual(
            linked[0]["godot_source_locations"],
            [{"path": "res://scripts/player.gd", "line": 27, "frame": "at: _ready (res://scripts/player.gd:27)"}],
        )

    def test_stack_frames_never_cross_editor_and_project_contexts(self):
        project_root = classify_event(
            "ERROR: project failed",
            timestamp="1000",
            context="godot_project_runtime",
        )
        editor_root = classify_event(
            "ERROR: editor failed",
            timestamp="1050",
            context="godot_web_editor_runtime",
        )
        project_frame = classify_event(
            "at: _ready (res://main.gd:5)",
            source_hint="browser_console",
            timestamp="1100",
            context="godot_project_runtime",
        )
        linked = link_continuation_events([project_root, editor_root, project_frame])
        self.assertEqual(linked[2]["related_event_index"], 0)
        self.assertEqual(linked[0]["godot_source_locations"][0]["line"], 5)
        self.assertNotIn("godot_source_locations", linked[1])

    def test_gdscript_backtrace_header_does_not_replace_root_error(self):
        context = "godot_project_runtime"
        root = classify_event(
            "ERROR: PROJECT_DIAG_FIXTURE: intentional runtime error",
            timestamp="1000",
            context=context,
        )
        cpp_frame = classify_event(
            "   at: push_error (core/variant/variant_utility.cpp:1023)",
            transport_type="error",
            source_hint="browser_console",
            timestamp="1100",
            context=context,
        )
        header = classify_event(
            "GDScript backtrace (most recent call first):",
            transport_type="error",
            source_hint="browser_console",
            timestamp="1200",
            context=context,
        )
        script_frame = classify_event(
            "       [0] _ready (res://main.gd:5)",
            transport_type="error",
            source_hint="browser_console",
            timestamp="1300",
            context=context,
        )
        print_frame = classify_event(
            "Frame 0 - res://main.gd:6 in function '_ready'",
            transport_type="log",
            source_hint="browser_console",
            timestamp="1400",
            context=context,
        )
        linked = link_continuation_events([root, cpp_frame, header, script_frame, print_frame])
        self.assertTrue(all(event.get("related_event_index") == 0 for event in linked[1:]))
        locations = {(item["path"], item["line"]) for item in linked[0]["godot_source_locations"]}
        self.assertEqual(locations, {("res://main.gd", 5), ("res://main.gd", 6)})
        self.assertEqual(summarize_events(linked)["severity_counts"]["error"], 1)
        self.assertEqual(linked[2]["classification_rule"], "godot.stack_trace.header")

    def test_continuation_outside_correlation_window_is_not_attached(self):
        root = classify_event("ERROR: worker failed", timestamp="1000")
        frame = classify_event(
            "   at: wait_to_finish (core/os/thread.cpp:84)",
            source_hint="browser_console",
            timestamp="2000000000",
        )
        linked = link_continuation_events([root, frame])
        self.assertNotIn("related_event_index", linked[1])

    def test_category_does_not_claim_root_cause(self):
        event = classify_event("ERROR: TCPServer listen failed")
        self.assertEqual(event["category"], "network")
        self.assertNotIn("root_cause", event)


if __name__ == "__main__":
    unittest.main()
