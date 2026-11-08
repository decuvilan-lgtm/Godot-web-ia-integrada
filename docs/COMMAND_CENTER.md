# Godot Command Center

## Estado verificado

- El relay FastAPI está desplegado en Render: `https://godot-web-ia-relay.onrender.com`.
- El último despliegue de código del relay usa el commit `8fa678ca342d828f4cd69a32f914922dbf9f85aa`. El commit más reciente de `main` incluye además documentación operativa.
- Neon Postgres está conectado al relay; el esquema `command_center` y el workspace `default` están disponibles.
- Neon Object Storage usa el bucket privado `godot-visual-captures`.
- En la última auditoría no había dispositivos emparejados, sesiones activas, comandos recientes ni activos visuales. El bucket estaba vacío.
- El pairing y la transferencia real todavía requieren una sesión del editor Godot Web aislado. Los tests de S3 son mocks y no demuestran una ida y vuelta real.
- Las órdenes visuales siguen deshabilitadas en el relay mediante `VISUAL_COMMANDS_ENABLED = False`.

Para emparejar y realizar la prueba controlada, seguir [LIVE_VISUAL_TRANSFER_RUNBOOK.md](LIVE_VISUAL_TRANSFER_RUNBOOK.md). No activar órdenes visuales generales para probarlas.

## Puestos y roles

- **`web_editor` — Godot Web de la IA:** puesto remoto aislado donde trabaja el agente.
- **`android_editor` — Godot Android del usuario:** editor y proyecto del usuario. No se utiliza para la prueba visual.
- **`agent_controller` — controlador IA:** identidad autorizada para encolar órdenes hacia un editor.
- **Neon Postgres:** fuente de verdad para workspaces, dispositivos, códigos, órdenes, resultados, revisiones, snapshots y eventos.
- **Neon Object Storage:** almacén privado de bytes de capturas. El navegador y el plugin nunca reciben credenciales S3.
- **Render:** relay/API y transporte. En el plan Free puede suspenderse por inactividad; Neon conserva el estado persistente.
- **GitHub:** código, cambios reproducibles y revisiones; no transporta cada comando del editor.

El workspace de IA y el editor Android permanecen separados. No emparejar Android para validar la captura visual.

## Base de datos y migraciones

El esquema `command_center` contiene:

- `workspaces`: identidad del proyecto y revisión aceptada.
- `devices`: editores Web/Android y controlador; se almacenan hashes de credenciales.
- `pairing_codes`: códigos de un solo uso con caducidad, almacenados como SHA-256.
- `sessions`: estado de conexión de dispositivos.
- `commands` y `command_results`: cola durable, idempotencia, leases y resultados.
- `revisions` y `snapshots`: historial y puntos de recuperación.
- `proposals` y `proposal_files`: cambios aislados pendientes de revisión.
- `events`: historial de eventos para auditoría y reconexión.
- `visual_sequences` y `visual_assets`: metadatos de capturas; los bytes viven en el bucket privado.

Migraciones visuales relevantes: `004_visual_observations.sql`, `005_visual_ui_sequences.sql` y `006_visual_asset_single_capture_idempotency.sql`, además de las migraciones base 001–003.

Workspace inicial: `default`. La identidad autenticada del dispositivo determina el workspace; el cliente no puede elegir otro workspace al consultar o capturar.

## Contrato de API

Rutas bajo `/v1/command-center`:

- `POST /pairing-codes`: requiere `X-Command-Center-Admin`; emite un código de un solo uso y corta duración.
- `POST /pair`: consume el código y registra o rota la credencial del dispositivo.
- `POST /commands`: solo `agent_controller`; crea una orden idempotente para `web_editor` o `android_editor`. Las órdenes visuales están bloqueadas actualmente.
- `GET /commands/next?target=web_editor|android_editor`: un editor reclama órdenes únicamente de su propio rol.
- `POST /commands/{id}/heartbeat`: renueva el lease de la orden reclamada.
- `POST /commands/{id}/result`: el editor confirma el resultado de su lease.
- `GET /commands/{id}`: consulta estado y resultado con autorización de workspace.

El relay conserva endpoints WebSocket heredados, pero el flujo durable nuevo es HTTP + Neon. No confundir ambos protocolos.

## Clientes de editor

### Godot Web — puesto de IA

El sandbox `examples/bridge-sandbox` incluye `addons/godot_command_center/plugin.gd`:

- Empareja como `web_editor`.
- Mantiene la credencial solo en memoria; no la escribe en el proyecto.
- Consulta la cola cada dos segundos y confirma resultados.
- La fase de lectura admite `ping`, `project.get_state`, `project.list_files`, `scene.inspect` y `script.read`.
- La captura visual implementada en el plugin obtiene imágenes de los SubViewports 2D y 3D; solo codifica JPEG o PNG.
- El plugin rechaza `editor_ui` y `game_preview` porque requieren captura del navegador, y rechaza `visual.zoom_to` hasta implementar restauración exacta de la vista.
- La implementación del plugin no implica que el flujo esté habilitado en el relay: la compuerta visual permanece cerrada.

### Godot Android — editor del usuario

El editor Android del usuario es un puesto distinto y no debe emparejarse ni modificarse durante la aceptación visual del editor Web. La habilitación futura de operaciones en Android requiere su propio alcance, pruebas y aprobación; no se deriva de la prueba del editor Web.

## Seguridad y consistencia

1. La revisión aceptada del proyecto Android nunca se sobrescribe por trabajo del agente.
2. El workspace Web del agente es una copia aislada.
3. Los cambios futuros se representan como propuestas con diff y revisión base.
4. Aplicar una propuesta exige aprobación explícita y coincidencia exacta de la revisión base.
5. Si la revisión cambió, la propuesta queda en conflicto y no se aplica.
6. Operaciones mutantes futuras deben ser idempotentes, auditables y tener snapshot/rollback.
7. Tokens y códigos se almacenan como hashes; no incluir secretos en proyectos, issues, capturas o logs.
8. Las notificaciones Realtime son pistas; los clientes consultan Postgres para recuperar órdenes tras reconectar.
9. No habilitar shell remoto, ejecución arbitraria ni escritura general de archivos en la fase de lectura.
10. El controlador IA y los dos editores tienen roles separados. Un editor nunca debe crear órdenes para sí mismo como si fuera el controlador.
11. El navegador/plugin envía bytes al relay; solo el relay accede a Neon S3 con credenciales del servidor.
12. El bucket de capturas permanece privado y la descarga pasa por autorización de workspace y rol.

## Siguientes hitos

1. Emparejar únicamente el editor Godot Web aislado.
2. Verificar que el dispositivo registrado sea `web_editor` en workspace `default` y que Android siga sin cambios.
3. Diseñar una autorización temporal estrictamente limitada a una única captura `editor_2d` para ese dispositivo; no habilitar todos los comandos visuales.
4. Probar subida, registro, descarga autenticada y coincidencia byte a byte/SHA-256.
5. Probar una secuencia corta de 2–3 imágenes y los estados de secuencia.
6. Confirmar que el navegador no contacta Neon S3 directamente.
7. Mantener la compuerta cerrada hasta completar la aceptación.
8. Después, conectar el controlador IA y avanzar hacia propuestas/diffs/snapshots/aprobación/rollback antes de permitir cambios al proyecto.
