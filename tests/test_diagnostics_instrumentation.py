from __future__ import annotations

import unittest

from diagnostics.instrument_godot import instrument_source, replace_once


class GodotInstrumentationTests(unittest.TestCase):
    def test_wait_marker_is_web_only_and_preserves_original_call(self):
        source = "\tthread.wait_to_finish();"
        result = replace_once(source, source, "Example::wait", "WAIT")
        self.assertIn("#ifdef WEB_ENABLED", result)
        self.assertIn('print_line("WEB_DIAG_WAIT_SITE:Example::wait");', result)
        self.assertIn("\tthread.wait_to_finish();", result)

    def test_tcp_marker_is_web_only(self):
        source = "\treturn server->listen(port, address);"
        result = instrument_source(source, [(source, "Example::listen")], "TCP")
        self.assertIn('WEB_DIAG_TCP_SITE:Example::listen', result)
        self.assertIn("#endif", result)

    def test_ambiguous_anchor_fails_instead_of_patching_multiple_sites(self):
        source = "\tthread.wait_to_finish();\n\tthread.wait_to_finish();"
        with self.assertRaises(ValueError):
            replace_once(source, "\tthread.wait_to_finish();", "ambiguous", "WAIT")


if __name__ == "__main__":
    unittest.main()
