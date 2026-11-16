# El sendero de las luciérnagas

A Godot 4.7.2 2D platform-adventure development benchmark. This is a playable vertical slice, not a startup-only sample.

## Run
1. Install Godot 4.7.2 and Python 3.
2. Install Pillow: `python3 -m pip install Pillow`.
3. Generate the original artwork: `python3 tools/generate_assets.py`.
4. Open this folder in Godot and run `scenes/main.tscn`.

The generated PNGs are deterministic outputs of the committed source generator. They are intentionally not checked into Git as opaque binary files.

## Controls
- A/D or arrow keys: move.
- Space/W/Up: jump.
- E/F: activate the crystal switch.
- Touch devices: on-screen controls are enabled automatically.

## Objectives
- Follow the gold fragments through the valley.
- Cross the raised platforms and avoid red thorn beds.
- Reach the midpoint checkpoint.
- Activate the pale crystal switch near the old arch.
- Pass the opened gate and enter the portal.
- There are 11 optional fragments.

## Systems
Player movement and animation, jump/gravity/collision, health and invulnerability, fall recovery, two patrol creatures, 11 pickups, crystal switch, gate, checkpoint, HUD, touch controls and final portal.

## Tests
`godot --headless --path . --editor --quit`
`godot --headless --path . --script res://tests/test_suite.gd`

See [level design](docs/LEVEL_DESIGN.md) for the objective flow and references.
