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

All routes are under `/v1/command-center/projects` and require a paired Bearer credential from `web_editor`, `android_editor`, or the separately paired `agent_controller`. The agent role is scoped to the same workspace and uses the same revision, hash, and conflict checks; it does not bypass the relay or receive Neon storage credentials.

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

1. In Godot Web, open **Compartir proyectos**, download the connector ZIP and import it into the web editor's Project Manager. Open that sandbox project; its Shared Projects dock is enabled by default.
2. In the admin page, create a temporary `web_editor` pairing code for the Shared Projects dock. Pair the Web dock with it.
3. In the modified Android editor, select the existing game project in Project Manager and press **Shared Sync**. This installs or repairs all three integration add-ons: Shared Projects, the read-only AI Bridge and Command Center. Open the project and pair its Shared Projects dock using a separate `android_editor` code in the same workspace.
4. In Android's Shared Projects dock, create a shared project, select it, Analyze the local-to-remote plan and press Synchronize to seed the remote project from the Android project.
5. In the Web sandbox, select that same shared project and press **Clonar remoto aquí**. Confirm only after checking the file count and size. This replaces the sandbox's syncable files with the Android project and saves local rescue copies under `user://godot_project_sync/rescue`.
6. The AI can now work in the cloned Web project. Analyze and Synchronize from Web to publish its changes to the shared store.
7. On Android, Analyze the incoming changes, review every listed path and press Synchronize only to approve that exact plan.

For an already-open Web project other than the connector sandbox, the two add-ons must also be installed and enabled in that project before pairing. The Web launcher downloads the connector sandbox; it does not silently modify another open project's files.

The separate `godot_command_center` dock has its own pairing flow for remote AI commands; pair it only on the Web editor. It is not required for file synchronization. The read-only AI Bridge WebSocket session is also separate from project-file sync.

Pairing credentials are kept in memory by each add-on and must be re-entered after an editor restart. Never paste admin credentials or pairing codes into a public issue or commit them to a project.

## Current implementation / verification status

- The Neon migration `007_shared_project_sync.sql` is applied to the production `production` branch.
- Relay API, project manifest/revision schema, editor add-on and Android Project Manager add-on installer are implemented in the feature branches.
- The web sandbox has the add-on enabled by default.
- The native Godot headless smoke test is included in both repositories' validation workflows.
- This does **not** yet prove a live two-device transfer. The feature must not be described as end-to-end validated until CI passes, the new relay commit is deployed, and one web editor plus one Android editor complete a real upload/download/hash round trip.
