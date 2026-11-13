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

## Sesiones persistentes de Godot Web

El navegador ya no se ejecuta en Render. El workflow de GitHub Actions inicia Chromium + Playwright en su runner Linux (16 GB RAM en el runner estándar público), importa el editor Godot Web y ejecuta la inspección desde esa máquina. Render queda como API ligera y pasarela de evidencias; no consume memoria de Chromium. Cada ejecución queda asociada a repositorio, rama, ruta y SHA completo e inmutable.

### Autenticación

Todas las rutas de `/v1/persistent-sessions` requieren un bearer token. Se aceptan:

- El secreto `PERSISTENT_SESSION_TOKEN` configurado en Render, para operaciones administrativas autorizadas.
- Un token OIDC emitido por GitHub Actions, validado contra la firma, emisor, audiencia, repositorio, workflow y rama permitidos.

Los valores predeterminados de OIDC corresponden a este repositorio, al workflow `.github/workflows/persistent-session-smoke.yml` y a `refs/heads/main`. No se deben copiar tokens OIDC ni secretos de Render a los proyectos de juego.

### API

- `GET /v1/persistent-sessions`: lista las sesiones activas del proceso.
- `POST /v1/persistent-sessions`: abre o reutiliza una sesión; resuelve la rama a un SHA si no se proporciona uno.
- `GET /v1/persistent-sessions/{id}`: consulta el estado y las tareas completadas.
- `POST /v1/persistent-sessions/{id}/heartbeat`: renueva el plazo de inactividad mientras una tarea autorizada está en curso.
- `GET /v1/persistent-sessions/{id}/profile`: obtiene el perfil de laboratorio del repositorio en el SHA importado.
- `POST /v1/persistent-sessions/{id}/profiles/{command}/run`: ejecuta una secuencia JSON validada y limitada, propiedad del repositorio del juego.
- `POST /v1/persistent-sessions/{id}/commands`: permite `inspect`, `screenshot`, `click_text` y teclas de una lista permitida.
- `POST /v1/persistent-sessions/worker-artifacts/{id}`: recibe un ZIP validado producido por el Browser Worker de GitHub Actions y lo persiste en Neon Object Storage.
- `GET /v1/persistent-sessions/{id}/artifacts/{artifact_id}`: recupera el paquete persistido.
- `DELETE /v1/persistent-sessions/{id}`: cierra explícitamente la sesión.

### Evidencias y persistencia

Los paquetes ZIP de tareas se guardan en el bucket privado Neon Object Storage `godot-visual-captures`. Incluyen `task-result.json`, eventos y capturas. El Relay guarda un SHA-256 en los metadatos del objeto y lo comprueba al descargarlo. Los paquetes no se duplican en la memoria de la sesión y pueden recuperarse después de un reinicio del proceso.

El Browser Worker crea el manifiesto, capturas y eventos en el runner; el Relay valida el ZIP, el SHA-256 y la identidad OIDC antes de guardarlo en Neon Object Storage. Después el worker descarga el mismo paquete y verifica su integridad con SHA-256 y CRC del ZIP.

### Perfiles propios de cada juego

Cada repositorio puede definir `godot-lab/lab-manifest.json`, su perfil de controles y comandos JSON. El Relay obtiene estos archivos desde el SHA importado, valida el esquema, las rutas y cada operación, y solo ejecuta interacciones de navegador incluidas en la lista permitida. No ejecuta shell, Python, JavaScript ni scripts externos suministrados por el proyecto. Cada perfil de controles y cada comando lleva un estado `pending`, `verified` u `obsolete`; para ejecutarse, ambos deben estar `verified` contra el SHA exacto importado. Una revisión nueva invalida automáticamente una verificación hecha contra otro SHA. El JSON válido por sí solo nunca significa que los controles hayan sido comprobados.

Si el repositorio no tiene un perfil válido, el laboratorio puede inspeccionar y capturar el editor, pero no inventa controles ni copia perfiles de otros juegos. Los repositorios de juegos siguen siendo la fuente de verdad; el Relay no modifica sus archivos.

### Límites operativos

- Chromium y su pestaña viven únicamente durante el job de GitHub Actions. Los runners hospedados son efímeros: no se promete conservar el mismo proceso entre jobs. La siguiente ejecución reconstruye el editor desde el mismo SHA exacto y registra esa reconstrucción en `checkpoint`.
- Los paquetes de evidencias sí son duraderos porque se guardan en Neon Object Storage.
- Render Free no aloja Chromium ni necesita memoria adicional para el navegador. El worker usa un único navegador/contexto por job y finaliza al terminar el trabajo.
- El navegador corre en modo headless dentro del runner de GitHub Actions; no es una simulación de Godot. Se carga y utiliza el editor Godot Web publicado.
- No se deben usar heartbeats, cron ni tráfico sintético para impedir la suspensión del plan Free. Una tarea explícita puede despertar el servicio; después se reconstruye una sesión nueva si la anterior ya no existe.
- El workflow instala Playwright/Chromium en el runner (con caché de binarios), abre/importa el proyecto, confirma el SHA informado por el conector, recoge evidencias, las guarda en Neon y verifica la recuperación del ZIP. El navegador se mantiene durante toda la ejecución activa; al terminar el job, GitHub destruye su runner y la próxima tarea reconstruye una sesión nueva.
