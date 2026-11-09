# Godot Shared Project Sync

This editor add-on connects a Godot project to the private, revisioned project store exposed by the Command Center relay. Install the same add-on in the Android Godot editor project to share files between the two editors.

## Pairing

1. Create a one-time pairing code for `web_editor` or `android_editor` in the Command Center admin page, using the same workspace for both editors.
2. Open the **Shared Projects** dock, confirm the relay URL, enter a device label and the temporary code, then pair.
3. Pair the other editor separately into that same workspace. Credentials are held only in memory and are discarded when the editor closes or disconnects.
4. Create a shared project from one editor, or select an existing shared project in the other.

## Safe synchronization

- **Analyze changes** only reads local files and the remote manifest. It does not modify files.
- **Synchronize now** recalculates the plan immediately before applying it.
- Each project has its own baseline manifest stored in the editor's `user://` data directory.
- SHA-256 hashes distinguish local and remote changes. If both sides changed the same file differently, the entire sync stops without applying any operation.
- Before a remote overwrite or deletion, the local file is copied into a rescue directory under `user://godot_project_sync/rescue/<project-id>/`.
- A baseline advances only after all operations finish and the server manifest is fetched again. If a transfer fails partway through, run Analyze again; already completed operations converge safely.
- The first sync can seed an empty remote project from local files or populate an empty local project from remote files. If both sides already contain different files at the same path and there is no baseline, those paths are reported as conflicts.

## Limits and exclusions

- Manual sync only; no background polling and no automatic upload.
- Maximum 500 operations per run, 10,000 files per project, and 32 MiB per file.
- `.git/`, `.godot/`, environment files, private keys, signing stores and provisioning profiles are excluded.
- Files are transferred only through the authenticated Render relay. Neon storage credentials never enter the editor.
- This first implementation does not merge text, resolve conflicts automatically, or synchronize editor settings and imported cache data.
