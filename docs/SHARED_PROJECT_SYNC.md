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
6. Once an AI runtime is connected to the Web project, it can work in the cloned project. Analyze and Synchronize from Web to publish its changes to the shared store.
7. On Android, Analyze the incoming changes, review every listed path and press Synchronize only to approve that exact plan.

For an already-open Web project other than the connector sandbox, the two add-ons must also be installed and enabled in that project before pairing. The Web launcher downloads the connector sandbox; it does not silently modify another open project's files.

The separate `godot_command_center` dock has its own pairing flow for remote AI commands; pair it only on the Web editor. It is not required for file synchronization. The read-only AI Bridge WebSocket session is also separate from project-file sync.

## GitHub Actions binary bridge (no custom MCP)

The project includes a GitHub Actions transport path for an assistant that can use the connected GitHub repository tools:

- The assistant creates a short-lived branch named `agent-transfer/<task-id>` and commits a request under `bridge-inbox/request.json`.
- For imports, binary payloads are Base64 text files under `bridge-inbox/payload/`. Large payloads may be split into multiple Base64 parts; each part must be a multiple-of-four Base64 segment and the request lists them in order.
- A push to the transfer branch triggers `.github/workflows/agent-binary-bridge.yml`.
- GitHub Actions obtains a short-lived OIDC assertion from GitHub. Render verifies the signature against GitHub's published JWKS and checks the fixed repository ID, owner ID, actor ID, workflow path, push event and `agent-transfer/*` ref before issuing a rotating `agent_controller` credential.
- The workflow uses that temporary credential with the existing project manifest/content/upload/delete routes. It never receives Neon database or Object Storage credentials.
- The temporary bridge device is revoked at the end of the workflow. Its token is also rotated on the next exchange and rejected after 30 minutes of inactivity.
- The workflow uploads a one-day GitHub Actions artifact. For exports, the artifact contains `bridge-export.zip` plus `bridge-result.json`; for imports, it contains the result report.

Export request:

```json
{"operation":"export","project_id":"<shared-project-uuid>"}
```

Import request:

```json
{
  "operation": "import",
  "project_id": "<shared-project-uuid>",
  "base_revision": 12,
  "files": [
    {
      "path": "scenes/player.tscn",
      "payload_parts": ["bridge-inbox/payload/player.part000.b64"],
      "base_sha256": "<previous-sha256-or-null>",
      "sha256": "<new-sha256>",
      "byte_size": 1234,
      "mime_type": "text/plain"
    }
  ],
  "deletes": []
}
```

The import script checks the whole-project base revision before changing anything, then checks every file's expected base hash and payload SHA-256. The existing Relay still enforces path restrictions, per-file 32 MiB limits, workspace ownership and revision conflict checks. The transfer script caps a batch at 500 operations and 512 MiB total. An interrupted multi-file import can leave earlier files committed; the returned report and the existing Analyze/reconcile workflow are used to recover safely.

This bridge does not use a custom MCP server and does not expose Neon credentials. It uses the existing GitHub connector for the request commit and artifact download, with GitHub Actions as an ephemeral transport worker.

## ChatGPT agent runtime status

The original direct ChatGPT-to-Relay runtime is still not present. The GitHub Actions bridge is a separate, connector-mediated path: it is available only after its Relay code and workflow are merged/deployed and its end-to-end project transfer is tested. A successful small binary fixture test does not prove a full Godot project import/export.

Pairing credentials are kept in memory by each add-on and must be re-entered after an editor restart. Never paste admin credentials or pairing codes into a public issue or commit them to a project.

## Current implementation / verification status

- The Neon migration `007_shared_project_sync.sql` is applied to the production `production` branch.
- Relay API, project manifest/revision schema, editor add-on and Android Project Manager add-on installer are implemented in the feature branches.
- The web sandbox has the add-on enabled by default.
- The native Godot headless smoke test is included in both repositories' validation workflows.
- This does **not** yet prove a live two-device transfer. The feature must not be described as end-to-end validated until the current Relay commit is deployed and one Web editor plus one Android editor complete a real upload/download/hash round trip.
- ChatGPT-to-Relay agent file transfer is a separate, unfinished integration milestone; the `agent_controller` API role alone does not complete it.
