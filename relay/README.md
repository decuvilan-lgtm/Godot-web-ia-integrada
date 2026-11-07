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
- `ALLOWED_ORIGINS`: optional comma-separated browser origins.

## API

- `GET /health`: liveness.
- `POST /v1/sessions`: requires `X-Admin-Token`; returns one-time editor and controller tokens.
- `GET /v1/sessions/{id}`: requires `Authorization: Bearer <controller_token>`.
- `POST /v1/sessions/{id}/request`: authenticated controller request; forwards a read-only protocol packet to the connected editor and waits for its response.
- `wss://host/v1/editor/{id}`: editor plugin connection. The first packet must be `{"type":"auth","protocol":1,"token":"..." }`.

## Current scope and limits

Only the bridge actions implemented by the plugin are usable: `ping`, `project.get_state`, `project.list_files`, `scene.inspect`, and `script.read`. Writes and arbitrary process execution are not exposed.

The free instance may sleep and its memory is ephemeral. A restart invalidates all sessions and tokens. Do not use it as project storage. A persistent workspace and snapshot system must be built separately before any write capability is enabled.
