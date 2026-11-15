import unittest

from semantic_controller import execute_semantic_command


class FakePage:
    def __init__(self):
        self.called = False

    def evaluate(self, script, payload):
        self.called = True
        return {"ok": True, "action": payload["command"]["action"]}


class SemanticControllerValidationTests(unittest.TestCase):
    def test_none_arguments_are_normalized_to_empty_object(self):
        page = FakePage()
        result = execute_semantic_command(page, "editor.get_state", None)
        self.assertTrue(page.called)
        self.assertTrue(result["ok"])

    def test_falsy_non_object_arguments_are_rejected_before_page_evaluate(self):
        for invalid in ([], "", 0, False):
            with self.subTest(invalid=invalid):
                page = FakePage()
                with self.assertRaises(ValueError):
                    execute_semantic_command(page, "editor.get_state", invalid)
                self.assertFalse(page.called)


if __name__ == "__main__":
    unittest.main()
