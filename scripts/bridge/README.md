# Browser command protocol

The browser worker controls the real Godot Web editor in Chromium. Commands are short JSON issue comments and are scoped to one issue/session. Every command must include protocol `1`, the exact `session_id`, and a strictly increasing `seq`.

## Allowlisted actions

- `status`: editor title, URL, viewport size, visible canvas bounds and short page text.
- `screenshot`: captures the current editor surface.
- `click_text`: clicks exact visible DOM text.
- `fill_placeholder`: fills an exact placeholder field.
- `assert_text`: verifies exact visible text.
- `canvas_click`: clicks a normalized point on the largest visible editor canvas.
- `canvas_drag`: sends a left-button path of 2-64 normalized points; `duration_ms` is limited to 50-5000.
- `canvas_scroll`: scrolls at a normalized canvas point; each delta is limited to -1200..1200.
- `press_key`: presses one key or shortcut from a fixed editing allowlist.
- `type_text`: types at most 500 characters into the currently focused control.
- `wait`: waits at most 20 seconds.
- `stop`: ends the bounded session.

Normalized coordinates use 0..1 relative to the largest visible canvas, not screen pixels. The status response includes its viewport-relative bounds so the controller can map screenshots to input points.

## Safety boundaries

The protocol does not accept arbitrary JavaScript, shell commands, URLs, selectors, file paths, or unbounded paths. The worker never commits to the game repository. Browser sessions are limited to 600 seconds and their logs, screenshots and task manifest are included in the evidence ZIP. The browser process is destroyed with the GitHub Actions runner when the job ends.