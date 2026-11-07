# Godot Web IA Relay

Small, ephemeral WebSocket/HTTP relay for pairing the Godot editor plugin with a remote controller.

## Runtime

- Python 3.12+
- FastAPI + Uvicorn
- Render free web service
- In-memory sessions only; all sessions expire after 30 minutes or process restart.
- No project files or source code are persisted by this service.

## Environment

- `RELAY_ADMIN_TOKEN`: required high-entropy secret used to create sessions.
- `SESSION_TTL_SECONDS`: optional, defaults to 1800.
- `ALLOWED_ORIGINS`: optional comma-separated browser origins; keep the deployed editor origin in this list.

## API

- `GET /health`: liveness.
- `POST /v1/sessions`: requires `X-Admin-Token`; returns one-time editor and controller tokens.
- `GET /v1/sessions/{id}`: requires `Authorization: Bearer <controller_token>`.
- `POST /v1/sessions/{id}/request`: authenticated controller request; forwards a read-only protocol packet to the connected editor and waits for its response.
- `wss://host/v1/editor/{id}`: editor plugin connection. The first packet must be `{"type":"auth","protocol":1,"token":"..." }`.

## Current scope and limits

Only the bridge actions implemented by the plugin are usable: `ping`, `project.get_state`, `project.list_files`, `scene.inspect`, and `script.read`. Writes and arbitrary process execution are not exposed.

The free instance may sleep and its memory is ephemeral. A restart invalidates all sessions and tokens. Do not use it as project storage. A persistent workspace and snapshot system must be built separately before any write capability is enabled.
## Neon Command Center API

The FastAPI relay also exposes a separate durable HTTP API backed by the `command_center` schema. It does not replace the ephemeral WebSocket session API above.

Required environment:
- `COMMAND_CENTER_DATABASE_URL`: Neon connection string for the dedicated `Godot Command Center` database. If missing, Command Center endpoints fail closed with HTTP 503. If Neon is temporarily unreachable at startup, the API retries pool initialization on later requests without requiring a relay restart.
- `COMMAND_CENTER_ADMIN_TOKEN`: separate high-entropy administrator secret for creating single-use device pairing codes.

Administrator page:
- Open `/command-center/admin` on the relay host to generate a pairing code without constructing an HTTP request manually.
- The page sends the admin secret only in the `X-Command-Center-Admin` request header, clears the password field after submission, and does not write credentials or codes to browser storage.
- The page and its same-origin script use no-store cache headers, a restrictive Content Security Policy, and no third-party assets. Keep the admin URL private and use it only over HTTPS.

Routes:
- `POST /v1/command-center/pairing-codes` — requires `X-Command-Center-Admin`; body: `{"device_kind":"android_editor","workspace":"default"}`. The returned code expires in 120 seconds.
- `POST /v1/command-center/pair` — exchanges a one-time code for a device bearer credential.
- `POST /v1/command-center/commands` — authenticated `agent_controller` queues an allowlisted read-only command with an idempotency key.
- `GET /v1/command-center/commands/next?target=android_editor` — an authenticated matching editor claims a leased command.
- `POST /v1/command-center/commands/{id}/result` — submits the command result.
- `GET /v1/command-center/commands/{id}` — reads command status within the authenticated workspace.

Only `ping`, `project.get_state`, `project.list_files`, `scene.inspect`, and `script.read` are enabled. Pairing codes are single-use; presenting a fresh administrator-issued code for an existing installation rotates its credential. Device credentials are stored only as SHA-256 hashes in Neon. Do not expose administrator secrets or device credentials in logs or project files.

Render remains on the free plan. The database URL is intentionally a manual secret (`sync: false`) in the Blueprint; no database credential is committed to this repository.
