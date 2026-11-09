# Agent binary bridge

This bridge moves binary Godot project files through the existing Render Relay and Neon project manifest. It uses GitHub Actions as the worker; no custom MCP server is required.

## Important: this repository is public

Files committed below `bridge-inbox/` and workflow artifacts may be visible to anyone with repository access. Use this route only for project content that is okay to publish. Never put credentials, API keys, private signing material, or environment files in a transfer request. The Relay rejects common secret and signing-file names as an additional guard.

## How a transfer is triggered

1. Create a branch named `agent-transfer/<task-name>` from `main`.
2. Commit `bridge-inbox/request.json` and any referenced Base64 payload files.
3. Push the branch. The workflow runs only for pushes in the `agent-transfer/**` namespace that change `bridge-inbox/**`.
4. Wait for the workflow to finish.
5. Download the artifact named `godot-agent-transfer-<run-id>`. It contains `bridge-result.json` and, for exports, `bridge-export.zip`.
6. Delete the transfer branch when finished. Workflow artifacts expire after one day.

The workflow file must already exist on the default branch before a transfer branch is pushed.

## Export a project from Neon

Create `bridge-inbox/request.json`:

```json
{
  "operation": "export",
  "project_id": "PROJECT_UUID"
}
```

The artifact's `bridge-export.zip` contains:

- `manifest.json`: project identity, snapshot revision, and per-file hashes.
- `files/<project-relative-path>`: original binary file bytes.

The exporter verifies each downloaded file's byte length and SHA-256, then checks that the project revision did not change during the snapshot.

## Import binary files into a project

Create `bridge-inbox/request.json`:

```json
{
  "operation": "import",
  "project_id": "PROJECT_UUID",
  "base_revision": 12,
  "files": [
    {
      "path": "art/sprites/hero.png",
      "byte_size": 12345,
      "sha256": "LOWERCASE_SHA256_OF_DECODED_BYTES",
      "mime_type": "image/png",
      "base_sha256": null,
      "payload_parts": [
        "bridge-inbox/payloads/hero.png.part-001.txt"
      ]
    }
  ],
  "deletes": []
}
```

Each payload part is an ASCII text file containing Base64 for a portion of the original binary file. Multiple parts are concatenated before Base64 decoding. The hash and byte size refer to the decoded binary bytes, not the Base64 text.

For an update, set `base_sha256` to the current file hash from the exported manifest. For a new file, use `null`. For a deletion, include the path and its current `base_sha256` in the `deletes` array.

The importer validates all payloads before sending one ZIP batch to Relay. Relay verifies the archive and hashes, checks `base_revision` and every file's base hash, then writes all manifest changes in one database transaction. A revision or file conflict rejects the entire batch; no subset is committed.

## Limits

- 32 MiB maximum per file.
- 512 MiB maximum uncompressed bytes per import/export batch.
- 500 file operations per import batch.
- 10,000 files in a project manifest.
- 1 MiB maximum ZIP manifest.
- Transfer artifact retention: one day.

## Authentication and storage

GitHub Actions obtains a short-lived OIDC token and exchanges it with Render Relay for a temporary `agent_controller` device credential. The workflow revokes that credential when it finishes. Neon credentials and Render secrets remain server-side; they are never committed to this repository or passed to the Godot editor.

All project bytes are stored in the existing private Neon Object Storage bucket. GitHub is the temporary task inbox and artifact handoff, not the source of truth for project revisions.
