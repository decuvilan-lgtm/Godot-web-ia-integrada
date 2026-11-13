# Godot Lab Profile Template

Copy this folder into a Godot game's repository as `godot-lab/`. The lab reads it at the same immutable commit SHA as the imported project.

## Files

- `lab-manifest.json`: declares the project path, control profile, and named command files.
- `control-profile.json`: stores this game's own control mapping and its verification state.
- `commands/*.json`: stores this game's own test sequences and individual verification states.
- Optional human-maintained companions: `CONTROL_PROFILE.md` and `TEST_HISTORY.md`.

## Verification contract

Every new profile and command starts as `pending` with a null `commit_sha`. A command cannot run merely because its JSON is valid.

After observing the actual game and repeating each interaction successfully, set its verification object to:

```json
{
  "status": "verified",
  "commit_sha": "FULL_SHA_OF_THE_EXACT_TESTED_PROJECT_COMMIT"
}
```

The control profile and each command are verified independently. The SHA must match the exact commit imported into Godot Web. If the project advances to another commit, an old verified profile automatically becomes `obsolete` until it is checked again. Do not copy a verified SHA forward to a new revision.

Allowed states: `pending`, `verified`, and `obsolete`. Record evidence and the tested SHA in `CONTROL_PROFILE.md` and `TEST_HISTORY.md`.

## Safety contract

These files are data, not executable scripts. The Relay accepts only a fixed set of generic browser operations. Shell commands, Python, JavaScript, arbitrary URLs, and external scripts are rejected. Keep each profile limited to the controls and interactions needed to test this game.

The manifest's `project.project_path` must match the project folder selected for import. Use an empty string for a project at the repository root.

## Supported command steps

- `wait`: `{"op":"wait","ms":500}` (0–5000 ms per step; 20 seconds total delay budget).
- `inspect`: record page text, canvas count, and connector status.
- `screenshot`: capture the current editor view into the task evidence.
- `assert_canvas`: require at least one canvas.
- `tap_control`: tap a named control from `control-profile.json`.
- `hold_control`: hold a named key control for at most 2 seconds.
- `click_text`: click exact visible text.
- `press_key`: press a key from the Relay's safe allowlist.
- `assert_text`: require a substring in visible page text.

Control types are `key`, `text`, and `point`. Point coordinates are normalized to the viewport (0–1), not absolute pixels.

## First-contact workflow

If a project has no profile, the lab records that it is missing and performs only generic inspection/capture. If a profile is pending or obsolete, it may inspect and capture but will not execute project-specific commands. Do not guess controls and do not copy another game's profile. Observe the actual interface, repeat interactions to verify them, then add the confirmed mapping and command files to this game's repository in a reviewed commit.
