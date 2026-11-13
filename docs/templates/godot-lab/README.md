# Godot Lab Profile Template

Copy this folder into a Godot game's repository as \`godot-lab/\`. The lab reads it at the same immutable commit SHA as the imported project.

## Files

- \`lab-manifest.json\`: declares the project path, control profile, and named command files.
- \`control-profile.json\`: stores this game's own control mapping.
- \`commands/*.json\`: stores this game's own test sequences.
- Optional human-maintained companions: \`CONTROL_PROFILE.md\` and \`TEST_HISTORY.md\`.

## Safety contract

These files are data, not executable scripts. The Relay accepts only a fixed set of generic browser operations. Shell commands, Python, JavaScript, arbitrary URLs, and external scripts are rejected. Keep each profile limited to the controls and interactions needed to test this game.

The manifest's \`project.project_path\` must match the project folder selected for import. Use an empty string for a project at the repository root.

## Supported command steps

- \`wait\`: \`{"op":"wait","ms":500}\` (0–5000 ms per step; 20 seconds total delay budget).
- \`inspect\`: record page text, canvas count, and connector status.
- \`screenshot\`: capture the current editor view into the task evidence.
- \`assert_canvas\`: require at least one canvas.
- \`tap_control\`: tap a named control from \`control-profile.json\`.
- \`hold_control\`: hold a named key control for at most 2 seconds.
- \`click_text\`: click exact visible text.
- \`press_key\`: press a key from the Relay's safe allowlist.
- \`assert_text\`: require a substring in visible page text.

Control types are \`key\`, \`text\`, and \`point\`. Point coordinates are normalized to the viewport (0–1), not absolute pixels.

## First-contact workflow

If a project has no profile, the lab records that it is missing and performs only generic inspection/capture. Do not guess controls and do not copy another game's profile. Observe the actual interface, repeat interactions to verify them, then add the confirmed mapping and command files to this game's repository in a reviewed commit.
