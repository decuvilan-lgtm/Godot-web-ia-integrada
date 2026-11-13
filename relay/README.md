# Godot Web IA Relay

Relay FastAPI para el laboratorio visual Godot Web. Render transporta las peticiones; Neon Postgres conserva identidades, cola, resultados y eventos; Neon Object Storage conserva bytes de capturas y archivos compartidos cuando el flujo los publica. El servicio permanece en el plan Free y puede suspenderse por inactividad.

## Rol del Relay

- Validar solicitudes de importación y rutas de proyectos.
- Descargar y preparar archivos de repositorios públicos para la importación web.
- Coordinar comandos y transferencias del Command Center.
- Transportar evidencia visual y resultados según las APIs habilitadas.
- No ser la fuente de verdad del proyecto Godot.
- No convertir la sesión web en un mecanismo de entrega del proyecto completo.

## Servicios y responsabilidades

- **Render Relay:** API HTTPS, autenticación, encolado, polling de clientes conectados y proxy de bytes.
- **Neon Postgres:** fuente de verdad para workspaces, dispositivos, pairing, comandos, resultados y eventos.
- **Neon Object Storage:** bucket privado para bytes de capturas y archivos compartidos.
- **Godot Web:** laboratorio visual, rol `web_editor`.
- **Godot Android:** puesto del usuario, rol `android_editor`.
- **GitHub:** fuente de verdad de código, recursos, ramas y commits.

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

El puente efímero `/v1/sessions/*` y `/v1/editor/*` está desactivado por defecto. El puente de producción es Command Center HTTP + Neon.

## Control desde ChatGPT

Las modificaciones permanentes del proyecto se realizan en su repositorio GitHub mediante el flujo autorizado. El editor web conserva su cliente HTTP del Command Center para sincronización y observación; no hay un runtime de ChatGPT conectado directamente a la cola.

## Emparejamiento

1. Abrir `/command-center/admin` por HTTPS.
2. Introducir el secreto administrativo en el campo de la página; no pegarlo en chats, archivos o código.
3. Elegir workspace `default` y el rol correspondiente (`web_editor` o `agent_controller`).
4. Generar el código solo cuando el dispositivo cliente esté listo: caduca en 120 segundos y se consume una vez.
5. Introducir el código en el cliente. El bearer devuelto se mantiene solo en memoria del plugin/cliente.

No generar códigos de pairing anticipadamente ni emparejar Android durante las pruebas del puesto Web.

## Sincronización e importación

GitHub es la fuente de verdad del proyecto. El Relay prepara una copia temporal para importarla en Godot Web; no es una vía para exportar el proyecto completo desde el editor.

Cada importación se identifica por repositorio, rama/ref, SHA y carpeta del proyecto. Cuando cambia el código o un recurso que se desea probar, GitHub Actions debe preparar y volver a cargar el proyecto actualizado. No se asume hot reload ni actualización automática de una pestaña ya abierta.

Si el commit no cambió, se pueden ejecutar más pruebas en la sesión activa. Si cambió, se importa la nueva revisión y se verifica su identidad antes de continuar.

## Evidencia y resultados

El laboratorio web entrega diagnósticos y evidencia, no el juego completo. Los resultados pueden incluir logs, mensajes del debugger disponibles, errores, advertencias, capturas, vídeo, frames, OCR, eventos, timeline, manifiestos y reportes JSON.

El proyecto completo se recupera desde el repositorio fuente usando el SHA registrado en el manifiesto. Los artefactos de evidencia deben almacenarse en Neon Object Storage u otro almacenamiento duradero configurado; no deben depender exclusivamente de memoria local del Relay.

## Sesiones persistentes de Godot Web

La API `/v1/persistent-sessions` administra una pestaña real de Chromium abierta contra el editor Godot Web desplegado. El navegador puede estar en modo headless, pero visita el servicio Godot Web real, no un editor simulado.

- `POST /v1/persistent-sessions`: abre el editor publicado para el proyecto seleccionado.
- `GET /v1/persistent-sessions/{id}`: consulta el estado de la sesión.
- `POST /v1/persistent-sessions/{id}/heartbeat`: extiende el TTL interno cuando se usa legítimamente; no debe emplearse para generar actividad artificial y evitar la suspensión de Render.
- `POST /v1/persistent-sessions/{id}/commands`: comandos visuales acotados, como `inspect`, `screenshot`, `click_text` y teclas permitidas.
- `POST /v1/persistent-sessions/{id}/tasks/complete`: empaqueta resultados de la tarea sin cerrar deliberadamente el navegador.
- `GET /v1/persistent-sessions/{id}/artifacts/{artifact_id}`: descarga el paquete de evidencia generado.
- `DELETE /v1/persistent-sessions/{id}`: cierre explícito.

Todas las rutas requieren `Authorization: Bearer $PERSISTENT_SESSION_TOKEN`. El token se configura como secreto en Render; nunca se incluye en el proyecto importado ni en el navegador.

### Contrato de sesión

Completar una tarea y cerrar una sesión son operaciones distintas. El cierre de tarea puede indicar `session_kept_open: true`; esto significa que el proceso no cerró deliberadamente el navegador. No garantiza que Render mantenga el servicio despierto.

Si el código fuente cambia, se vuelve a ejecutar el workflow de importación para cargar el nuevo SHA. La sesión abierta no se considera automáticamente sincronizada.

### Suspensión y recuperación

Render Free puede suspender el servicio por inactividad. No se deben crear cron jobs, heartbeats artificiales ni sondeos periódicos para impedirlo. La activación ocurre solo por una nueva solicitud explícita de trabajo.

Después de una suspensión/reinicio, no se promete conservar la pestaña ni el estado en memoria de Chromium. El flujo vuelve a despertar el servicio, reconstruye el entorno e importa la revisión identificada en GitHub. Los resultados ya generados deben haberse publicado en almacenamiento duradero antes de dar por finalizada la tarea.

### Límites y estado real

- El TTL de la aplicación es una regla interna, no una garantía sobre la duración de Render.
- La capacidad de sesiones simultáneas está limitada por la configuración del servicio.
- Chromium se instala durante el build de Render.
- El proceso local y su memoria pueden desaparecer al suspenderse o reiniciarse el servicio.
- El paquete de evidencia tiene límites de tamaño; no contiene el proyecto entero.
- El API solo permite acciones acotadas; no acepta JavaScript arbitrario ni URLs de navegación suministradas por el usuario.
- La persistencia real de resultados depende del almacenamiento duradero configurado y verificado.

## Operación y límites

- Las órdenes del Command Center expiran a los 10 minutos; los leases se renuevan por el editor.
- La misma clave idempotente con el mismo contenido devuelve la orden existente; reutilizarla con contenido diferente produce conflicto.
- El bucket de capturas permanece privado. El navegador no recibe credenciales S3.
- No se habilita escritura remota del proyecto aceptado. Cualquier futuro cambio requiere propuestas, diff, snapshot, validación y aprobación explícita.
- La importación Web acepta archivos fuente de repositorio de hasta 256 MiB y entrega ZIPs de hasta 128 MiB; los ejecutables ELF nativos se omiten solo del paquete temporal Web, nunca del repositorio original. La respuesta informa las exclusiones en `X-Godot-Web-Excluded-*`.
- Mantener Render en el plan Free.
