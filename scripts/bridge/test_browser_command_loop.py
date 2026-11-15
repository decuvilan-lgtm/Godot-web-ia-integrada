import unittest
from unittest.mock import patch
import browser_command_loop
from browser_command_loop import _bounded_duration_seconds, _fetch_new_comments, _ordered_comments, _validate

SESSION="issue-test"

class BrowserCommandValidationTests(unittest.TestCase):
    def command(self, action, **fields):
        return {"protocol":1,"session_id":SESSION,"seq":1,"action":action,**fields}

    def test_normalized_canvas_click_is_accepted(self):
        self.assertEqual(_validate(self.command("canvas_click",x=0.5,y=1.0),SESSION,0),(1,"canvas_click"))

    def test_canvas_drag_accepts_bounded_path(self):
        cmd=self.command("canvas_drag",points=[[0.1,0.2],[0.5,0.6],[0.9,0.8]],duration_ms=600)
        self.assertEqual(_validate(cmd,SESSION,0),(1,"canvas_drag"))

    def test_canvas_click_rejects_out_of_bounds_coordinates(self):
        with self.assertRaises(ValueError):
            _validate(self.command("canvas_click",x=1.01,y=0.5),SESSION,0)

    def test_canvas_click_rejects_extremely_large_coordinates(self):
        with self.assertRaises(ValueError):
            _validate(self.command("canvas_click",x=10**1000,y=0.5),SESSION,0)

    def test_canvas_drag_rejects_unbounded_path(self):
        points=[[0.5,0.5] for _ in range(65)]
        with self.assertRaises(ValueError):
            _validate(self.command("canvas_drag",points=points),SESSION,0)

    def test_canvas_drag_rejects_malformed_points(self):
        with self.assertRaises(ValueError):
            _validate(self.command("canvas_drag",points=[[0.5,0.5],[2,0.5]]),SESSION,0)

    def test_press_key_uses_allowlist(self):
        self.assertEqual(_validate(self.command("press_key",key="Escape"),SESSION,0),(1,"press_key"))
        with self.assertRaises(ValueError):
            _validate(self.command("press_key",key="Alt+F4"),SESSION,0)

    def test_type_text_is_bounded(self):
        self.assertEqual(_validate(self.command("type_text",text="BridgeSandbox"),SESSION,0),(1,"type_text"))
        with self.assertRaises(ValueError):
            _validate(self.command("type_text",text="x"*501),SESSION,0)

    def test_canvas_scroll_accepts_bounded_deltas(self):
        cmd=self.command("canvas_scroll",x=0.5,y=0.5,delta_y=-600)
        self.assertEqual(_validate(cmd,SESSION,0),(1,"canvas_scroll"))

    def test_canvas_scroll_rejects_excessive_deltas(self):
        cmd=self.command("canvas_scroll",x=0.5,y=0.5,delta_y=1201)
        with self.assertRaises(ValueError):
            _validate(cmd,SESSION,0)

    def test_unknown_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            _validate(self.command("canvas_click",x=0.5,y=0.5,script="alert(1)"),SESSION,0)

    def test_duration_is_clamped_to_requested_limit(self):
        self.assertEqual(_bounded_duration_seconds(180),180)
        self.assertEqual(_bounded_duration_seconds(600),600)
        self.assertEqual(_bounded_duration_seconds(900),600)
        self.assertEqual(_bounded_duration_seconds(-10),0)

    def test_duration_rejects_bool_and_non_integer_values(self):
        for value in (True, False, 1.5, "180", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _bounded_duration_seconds(value)

    def test_descending_api_comments_are_processed_oldest_first(self):
        comments = [{"id": 300}, {"id": 200}, {"id": 100}]
        self.assertEqual([item["id"] for item in _ordered_comments(comments)], [100,200,300])

    @patch("browser_command_loop._api")
    def test_comment_pagination_reads_all_new_pages_without_replaying_old(self, api):
        api.side_effect = [
            [{"id": value} for value in range(300, 200, -1)],
            [{"id": value} for value in range(200, 100, -1)],
        ]
        comments = _fetch_new_comments("https://api.invalid/comments?per_page=100", "token", 150)
        self.assertEqual([item["id"] for item in comments], list(range(151, 301)))
        self.assertEqual(api.call_count, 2)
        self.assertIn("page=2", api.call_args_list[1].args[0])

if __name__=="__main__":
    unittest.main()
