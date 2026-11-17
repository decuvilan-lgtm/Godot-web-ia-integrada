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
- `run_game`: starts the active scene with F6.
- `game_view`: opens the Game tab and detects the preview canvas.
- `game_click`: clicks a normalized point inside the running game.
- `game_input`: holds one allowlisted key for 50-5000 ms and always releases it.
- `semantic_command`: sends a native editor action (`editor.get_state`, `editor.list_capabilities`, `scene.get_tree`, `scene.inspect_node`, `scene.add_node`, or `scene.set_property`).
- `stop`: ends the bounded session.

Normalized coordinates use 0..1 relative to the largest visible canvas, not screen pixels. The status response includes its viewport-relative bounds so the controller can map screenshots to input points.

## Safety boundaries

The protocol does not accept arbitrary JavaScript, shell commands, URLs, selectors, file paths, or unbounded paths. The worker never commits to the game repository. Browser sessions are configurable from 60 to 3600 seconds (1800 seconds by default); the host can be stopped early with `stop`. Logs, screenshots and the task manifest are included in the evidence ZIP. The browser process is destroyed with the GitHub Actions runner when the job ends.

## Semantic scene authoring

`scene.add_node` accepts only allowlisted Godot node classes and a validated relative parent path. `scene.set_property` accepts a validated relative node path, an Inspector property name and one bounded JSON value. Numeric arrays represent Vector2/Vector2i/Vector3/Color values; resource properties use an object with exactly one `resource_path` field pointing inside `res://`. Each mutation uses the editor undo manager and never saves automatically.

The operator's `semantic-build` request accepts 1-12 node specifications. Each may include a `properties` object with up to 12 values. The operator verifies the new nodes in `scene.get_tree` and reads configured properties back with `scene.inspect_node` before reporting success.

## Running-game preview

The same Chromium session can run the scene with F6, open Game, detect the visible game canvas, click at normalized coordinates and hold approved keyboard inputs. A canvas screenshot can be returned inline while the editor session remains open. This preview input channel is separate from semantic editor mutations.
