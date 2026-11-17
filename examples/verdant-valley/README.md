# El sendero de las luciérnagas

A Godot 4.7.2 2D platform-adventure development benchmark. This is a playable vertical slice, not a startup-only sample.

## Run
1. Install Godot 4.7.2 and Python 3.
2. Install Pillow: `python3 -m pip install Pillow`.
3. Generate the original artwork: `python3 tools/generate_assets.py`.
4. Open this folder in Godot and run `scenes/main.tscn`.

The generated PNGs are deterministic outputs of the committed source generator. They are intentionally not checked into Git as opaque binary files. Workflow A runs the generator and overlays those PNGs into the project archive before the browser imports it, so the remote preview receives the same art without adding generated binaries to the repository.

## Controls
- A/D or arrow keys: move.
- Space/W/Up: jump.
- E/F: activate the crystal switch.
- Touch devices: visible on-screen movement, jump and interaction buttons are enabled automatically.
- Jump has a short input buffer and coyote time; releasing the button early makes a shorter hop.

## Objectives
- Follow the gold fragments through the valley.
- Cross the raised platforms and avoid red thorn beds.
- Reach the midpoint checkpoint.
- Use the restorative crystal beside the midpoint checkpoint if health is missing; it restores up to two hearts.
- Activate the pale crystal switch near the old arch.
- Pass the opened gate and enter the portal.
- There are 11 optional fragments.

## Systems
Player movement with coyote time, jump buffering and variable jump height; aligned capsule/sprite feet; health, invulnerability and directional knockback; fall recovery; two patrol creatures; 11 animated fragments; one restorative crystal; crystal switch, sealed gate, checkpoint, HUD, visible touch controls and animated final portal.

## Tests
`godot --headless --path . --editor --quit`
`godot --headless --path . --script res://tests/test_suite.gd`

See [level design](docs/LEVEL_DESIGN.md) for the objective flow and references.
