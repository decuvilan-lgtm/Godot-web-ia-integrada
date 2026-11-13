import unittest
from browser_command_loop import _validate

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

    def test_unknown_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            _validate(self.command("canvas_click",x=0.5,y=0.5,script="alert(1)"),SESSION,0)

if __name__=="__main__":
    unittest.main()
