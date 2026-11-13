# Godot Web IA Relay

Relay FastAPI para el Godot Command Center. Render transporta las peticiones; Neon Postgres conserva identidades, cola, resultados y eventos. El servicio permanece en el plan Free y puede suspenderse por inactividad.

## Servicios y responsabilidades

- **Render Relay:** API HTTPS, autenticación, encolado, polling y proxy de bytes.
- **Neon Postgres:** fuente de verdad para workspaces, dispositivos, pairing, comandos, resultados y eventos.
- **Neon Object Storage:** bucket privado para bytes de capturas y archivos compartidos.
- **Godot Web:** puesto aislado de la IA, rol `web_editor`.
- **Godot Android:** puesto del usuario, rol `android_editor`.

## Variables de entorno

- `COMMAND_CENTER_DATABASE_URL`: URL de Neon.
- `COMMAND_CENTER_ADMIN_TOKEN`: secreto administrativo para emitir códigos de emparejamiento.
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_REGION`: acceso del relay al bucket privado.
- `ALLOWED_ORIGINS`: orígenes permitidos para clientes de navegador.
- `RELAY_LEGACY_BRIDGE_ENABLED`: desactivado por defecto. Solo habilita temporalmente el puente WebSocket antiguo; no debe activarse en producción.

No se guardan secretos en el repositorio. No registrar tokens, códigos temporales, URLs firmadas ni credenciales S3.

## API principal

- `GET /health`: liveness del relay y estado de inicialización de Neon.
- `GET /v1/github/{owner}/{repository}/archive`: descarga acotada del ZIP público de la rama solicitada para precarga del Project Manager Godot Web. Acepta `branch` y `path`; reempaqueta subcarpetas para dejar `project.godot` en la raíz del ZIP.
- `/v1/command-center/*`: emparejamiento, órdenes, leases, resultados y consulta.
- `/v1/command-center/visual/*`: transferencias autenticadas de capturas.
- `/v1/command-center/projects/*`: sincronización de proyectos compartidos.
- `/command-center/admin`: página same-origin para emitir códigos temporales.

El puente efímero `/v1/sessions/*` y `/v1/editor/*` está desactivado por defecto. El único puente de producción es Command Center HTTP + Neon.

## Control desde ChatGPT

Las modificaciones del repositorio se realizan mediante la integración de GitHub. El editor web conserva su cliente HTTP del Command Center para sincronización y observación; no hay un runtime de ChatGPT conectado directamente a la cola.

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
- No se habilita escritura remota del proyecto aceptado. Cualquier futuro cambio requiere propuestas, diff, snapshot, validación y aprobación explícita.
- La importación Web acepta archivos fuente de repositorio de hasta 256 MiB y entrega ZIPs de hasta 128 MiB; los ejecutables ELF nativos se omiten solo del paquete temporal Web, nunca del repositorio original. La respuesta informa las exclusiones en `X-Godot-Web-Excluded-*`.
- Mantener Render en el plan Free.
