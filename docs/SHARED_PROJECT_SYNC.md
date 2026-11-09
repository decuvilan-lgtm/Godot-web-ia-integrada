# Shared Godot project synchronization

## Purpose

Godot Web and the modified Godot Android editor can open the same named project from one Command Center workspace. They remain separate editor installations and keep independent local copies. Synchronization is explicit and file-based; there is no background mirroring.

## Architecture

- Godot Web and Android use the same `godot_project_sync` EditorPlugin.
- Each editor pairs independently as `web_editor` or `android_editor` into the same workspace.
- A workspace can contain multiple shared projects, each with a UUID, slug, file manifest and monotonically increasing revision.
- Neon Postgres stores project metadata, current file hashes and a revision/change log.
- File bytes are content-addressed in the existing private Neon Object Storage bucket under the `projects/` prefix.
- All byte transfers pass through the authenticated Render relay. Editor clients never receive S3 URLs or Neon credentials.

## API

All routes are under `/v1/command-center/projects` and require a paired editor Bearer credential.

- `GET /`: list projects in the authenticated workspace.
- `POST /`: create a project with a workspace-scoped slug.
- `GET /{project_id}/manifest`: read the current file manifest and head revision.
- `GET /{project_id}/changes?since_revision=N`: read ordered file changes after a revision.
- `POST /{project_id}/files?path=...`: upload one file. Optional `X-Base-SHA256` is the expected current remote hash; `X-File-SHA256` is verified by the relay.
- `POST /{project_id}/files/delete?path=...`: create a tombstone using required `X-Base-SHA256`.
- `GET /{project_id}/files/content?path=...`: download bytes through the relay and verify the stored hash.

The server checks workspace ownership on every operation, rejects stale file bases with HTTP 409, validates relative POSIX paths, and excludes Git metadata, Godot cache data, environment files and common signing credentials. Maximums: 32 MiB per file, 10,000 files per project, 2,000 change rows per request. The editor plug-in applies at most 500 operations per manual sync.

## Client synchronization algorithm

1. Analyze hashes local files and fetches the remote manifest. It does not write files and displays the exact paths and directions in a review panel.
2. Each editor stores its own last-successful per-project baseline under `user://godot_project_sync/baselines`.
3. The plan compares local, remote and baseline hashes to distinguish local-only changes, remote-only changes, converged files and conflicts.
4. If both sides changed one path differently, the whole plan stops. No automatic last-writer-wins behavior is used.
5. Sync is an explicit approval of the reviewed plan. Immediately before applying, the client recomputes a fingerprint containing the remote head revision and every operation. If anything changed since Analyze, Sync is blocked and the user must review a fresh plan.
6. Before a remote overwrite or deletion, the local copy is rescued under `user://godot_project_sync/rescue/<project-id>/`.
7. Uploads, downloads and deletes use expected remote hashes. Downloads are hash-verified and staged before replacement.
8. The baseline advances only after all operations succeed and a fresh remote manifest is read. If a batch fails partway through, the baseline remains unchanged and a subsequent Analyze can reconcile completed operations.

Renames are represented as a delete plus an add in the first implementation. Text merge and automatic conflict resolution are intentionally out of scope.

## Pairing and use

1. In the admin page, create one temporary pairing code for `web_editor` and another for `android_editor`, both using the same workspace.
2. Open the **Shared Projects** dock in the Godot Web sandbox and pair it with the web code.
3. In the modified Android editor, select one project in Project Manager and press **Shared Sync**. This installs and enables the same add-on in that project. Open the project and pair it with the Android code.
4. Create a shared project from either editor; select the same project from the other editor's list.
5. Use **Analyze changes** before **Synchronize now**.

Pairing credentials are kept in memory by the add-on and must be re-entered after an editor restart. Never paste admin credentials or pairing codes into a public issue or commit them to a project.

## Current implementation / verification status

- The Neon migration `007_shared_project_sync.sql` is applied to the production `production` branch.
- Relay API, project manifest/revision schema, editor add-on and Android Project Manager add-on installer are implemented in the feature branches.
- The web sandbox has the add-on enabled by default.
- The native Godot headless smoke test is included in both repositories' validation workflows.
- This does **not** yet prove a live two-device transfer. The feature must not be described as end-to-end validated until CI passes, the new relay commit is deployed, and one web editor plus one Android editor complete a real upload/download/hash round trip.
