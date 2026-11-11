# Godot Web IA Relay

Relay FastAPI para el Godot Command Center. Render transporta las peticiones; Neon Postgres conserva identidades, cola, resultados y eventos. El servicio permanece en el plan Free y puede suspenderse por inactividad.

## Servicios y responsabilidades

- **Render Relay:** API HTTPS, autenticación, encolado, polling y proxy de bytes.
- **Neon Postgres:** fuente de verdad para workspaces, dispositivos, pairing, comandos, resultados y eventos.
- **Neon Object Storage:** bucket privado para bytes de capturas y archivos compartidos.
- **Godot Web:** puesto aislado de la IA, rol `web_editor`.
- **Godot Android:** puesto del usuario, rol `android_editor`.
- **MCP:** interfaz estándar para hosts/agentes externos, rol `agent_controller`.

## Variables de entorno

- `COMMAND_CENTER_DATABASE_URL`: URL de Neon.
- `COMMAND_CENTER_ADMIN_TOKEN`: secreto administrativo para emitir códigos de emparejamiento.
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_REGION`: acceso del relay al bucket privado.
- `ALLOWED_ORIGINS`: orígenes permitidos para clientes de navegador.
- `RELAY_LEGACY_BRIDGE_ENABLED`: desactivado por defecto. Solo habilita temporalmente el puente WebSocket antiguo; no debe activarse en producción.

No se guardan secretos en el repositorio. No registrar tokens, códigos temporales, URLs firmadas ni credenciales S3.

## API principal

- `GET /health`: liveness del relay y estado de inicialización de Neon.
- `/v1/command-center/*`: emparejamiento, órdenes, leases, resultados y consulta.
- `/v1/command-center/visual/*`: transferencias autenticadas de capturas.
- `/v1/command-center/projects/*`: sincronización de proyectos compartidos.
- `GET /v1/github/import/{owner}/{repo}`: descarga acotada de repositorios públicos; el Relay valida la visibilidad pública y sigue únicamente redirecciones a `codeload.github.com`.
- `/command-center/admin`: página same-origin para emitir códigos temporales.

El puente efímero `/v1/sessions/*` y `/v1/editor/*` está desactivado por defecto. El único puente de producción es Command Center HTTP + Neon.

## Servidor MCP remoto

Endpoint Streamable HTTP:

`https://godot-web-ia-relay.onrender.com/mcp`

El MCP exige `Authorization: Bearer <credencial de dispositivo>` y solo acepta dispositivos `agent_controller`. El token se valida contra el hash guardado en Neon en cada petición. El middleware rechaza credenciales ausentes, inválidas, revocadas o de otro rol antes de procesar MCP.

Herramientas:

- `godot_workspace_status`
- `godot_enqueue_command`
- `godot_command_status`
- `godot_list_recent_commands`

El MCP comparte la misma cola `command_center.commands` que la API REST. El destino de los comandos MCP está fijado a `web_editor`. La idempotencia, los límites de tamaño y la política de comandos se validan antes de insertar. El servidor no crea workspaces ni sesiones por consulta.

La política permite las cinco acciones de lectura del plugin y las capturas `visual.capture` / `visual.capture_sequence` para `editor_2d` y `editor_3d`. No permite escritura, shell, ejecución de procesos ni zoom de coordenadas.

**Importante:** el despliegue de un servidor MCP no lo registra automáticamente en ChatGPT. Un host externo compatible debe configurarlo y recibir una credencial `agent_controller` por el flujo de emparejamiento. No generar códigos hasta que el cliente esté listo.

## Emparejamiento

1. Abrir `/command-center/admin` por HTTPS.
2. Introducir el secreto administrativo en el campo de la página; no pegarlo en chats, archivos o código.
3. Elegir workspace `default` y el rol correspondiente (`web_editor` o `agent_controller`).
4. Generar el código solo cuando el dispositivo cliente esté listo: caduca en 120 segundos y se consume una vez.
5. Introducir el código en el cliente. El bearer devuelto se mantiene solo en memoria del plugin/cliente.

No generar códigos de pairing anticipadamente ni emparejar Android durante las pruebas del puesto Web.

## Operación y límites

- Neon es la fuente persistente; Render no almacena la cola en memoria.
- Las órdenes expiran a los 10 minutos; los leases se renuevan por el editor.
- La misma clave idempotente con el mismo contenido devuelve la orden existente; reutilizarla con contenido diferente produce conflicto.
- El bucket de capturas permanece privado. El navegador no recibe credenciales S3.
- El proxy GitHub acepta solo nombres owner/repository, limita los ZIP a 64 MiB, aplica un límite de 8 solicitudes por IP cada 10 minutos y mantiene un máximo de 3 descargas concurrentes. No acepta URLs arbitrarias ni tokens GitHub.
- No se habilita escritura remota del proyecto aceptado. Cualquier futuro cambio requiere propuestas, diff, snapshot, validación y aprobación explícita.
- Mantener Render en el plan Free.
