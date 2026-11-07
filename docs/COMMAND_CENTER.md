# Godot Command Center

## Puestos y roles

- **`web_editor` — Godot Web de la IA:** puesto remoto desplegado en Render. La IA trabaja sobre un workspace aislado; no es el editor móvil del usuario.
- **`android_editor` — Godot Android del usuario:** editor del usuario en su teléfono y propietario del proyecto aceptado.
- **`agent_controller` — controlador IA:** identidad de servicio autorizada para encolar órdenes hacia uno de los editores.
- **Neon Postgres:** fuente de verdad para workspaces, dispositivos, códigos, órdenes, resultados, revisiones, snapshots, propuestas y eventos.
- **Render Free:** relay/API y transporte. Puede suspenderse y reiniciarse; no almacena estado autoritativo.
- **GitHub:** código, parches reproducibles y revisiones. No es el transporte de cada comando del editor.

La IA usa Godot Web. El usuario usa Godot Android. Nunca se debe pedir al usuario que sustituya su editor móvil por la web, ni utilizar el dispositivo Android como puesto de trabajo de la IA.

## Base de datos

Migraciones:

- `database/migrations/001_command_center.sql`
- `database/migrations/002_live_link_command_leases.sql`
- `database/migrations/003_require_command_idempotency_keys.sql`

El esquema `command_center` está instalado en el proyecto Neon `Godot Command Center`, base `neondb`. Incluye:

- `workspaces`: identidad del proyecto y revisión aceptada.
- `devices`: editores Android/Web y controlador IA. Solo hashes de tokens.
- `pairing_codes`: códigos temporales de un solo uso, almacenados como SHA-256.
- `sessions`: sesiones y caducidad de dispositivos.
- `commands` y `command_results`: cola durable, idempotencia, leases y resultados.
- `revisions` y `snapshots`: historial y puntos de recuperación.
- `proposals` y `proposal_files`: cambios aislados pendientes de revisión.
- `events`: historial append-only para auditoría y reconexión.

Workspace inicial: `default` / `Godot Android Workspace`.

## Contrato de API implementado en PR #1

El relay FastAPI añade rutas bajo `/v1/command-center`:

- `POST /pairing-codes`: requiere `X-Command-Center-Admin`; emite un código de un solo uso.
- `POST /pair`: consume un código y registra/rota la credencial del dispositivo.
- `POST /commands`: solo `agent_controller`; crea una orden idempotente.
- `GET /commands/next?target=web_editor|android_editor`: un editor reclama una orden de su propio rol.
- `POST /commands/{id}/result`: el editor confirma el resultado de su lease.
- `GET /commands/{id}`: consulta estado y resultado con autorización de workspace.

La API conserva los endpoints WebSocket heredados, pero el nuevo flujo durable es HTTP + Neon. No se deben confundir ambos protocolos.

## Clientes de editor

### Godot Web — puesto de la IA

El sandbox `examples/bridge-sandbox` habilita `addons/godot_command_center/plugin.gd`:

- Empareja con rol `web_editor`.
- Mantiene el token solo en memoria.
- Consulta la cola durable cada dos segundos.
- Confirma resultados y conserva un resultado pendiente ante fallos transitorios.
- Limita las acciones a `ping`, `project.get_state`, `project.list_files`, `scene.inspect` y `script.read`.
- No escribe archivos ni ejecuta shell/procesos.

El sandbox debe importarse/abrirse en el editor web para cargar el complemento. La mera existencia del ZIP o el smoke test headless no prueba pairing real ni control del navegador.

### Godot Android — puesto del usuario

El PR #3 del repositorio Android incorpora el cliente de cola al addon Live Link existente:

- Empareja con rol `android_editor`.
- Usa el mismo contrato de órdenes/resultados.
- Token solo en memoria; tras reiniciar, debe emparejarse de nuevo.
- Solo inspección y lectura en la primera fase.

El cambio se mantiene en un patcher/workflow reproducible porque el repositorio Android descarga el árbol upstream durante la compilación.

## Seguridad y consistencia

1. La revisión aceptada del proyecto Android nunca se sobrescribe por trabajo del agente.
2. El workspace web del agente es una copia aislada.
3. Todo cambio futuro se representa como propuesta con diff y revisión base.
4. Aplicar una propuesta exige aprobación explícita y coincidencia exacta de la revisión base.
5. Si la revisión cambió, la propuesta queda en conflicto y no se aplica.
6. Operaciones mutantes futuras deben ser idempotentes, auditables y tener snapshot/rollback.
7. Tokens y códigos se almacenan como hashes; no incluir secretos en proyectos o logs.
8. Las notificaciones Realtime son pistas. Los clientes deben consultar Postgres para recuperar órdenes tras reconectar.
9. No habilitar shell remoto, ejecución arbitraria ni escritura general de archivos en la fase de lectura.
10. El controlador IA y los dos editores tienen roles separados. Un editor nunca debe crear órdenes para sí mismo como si fuera el controlador.

## Estado de despliegue

- Migraciones 001–003: aplicadas y verificadas en Neon.
- Workspace default: creado.
- Relay FastAPI: implementación en PR #1, todavía borrador.
- Cliente Android: implementación en PR #3, todavía borrador.
- Cliente Web: añadido al sandbox en PR #1.
- Render: no se han configurado aún `COMMAND_CENTER_DATABASE_URL` ni `COMMAND_CENTER_ADMIN_TOKEN`; no se ha desplegado la versión nueva.
- Dispositivos emparejados: ninguno.
- Órdenes reales y resultados: ninguno.
- Prueba de extremo a extremo: pendiente.
- Escritura/propuestas/aplicación: todavía no habilitadas.

## Próximos pasos

1. Validar el complemento web en el Godot Web real.
2. Revisar y desplegar el relay con las credenciales Neon en Render Free.
3. Emparejar el editor web como `web_editor`.
4. Emparejar el Godot Android del usuario como `android_editor`.
5. Verificar una orden `ping` y después las cuatro operaciones de lectura.
6. Construir y conectar el controlador IA autenticado para emitir órdenes al workspace web.
7. Implementar propuestas/diffs/snapshots/validación/aprobación/rollback antes de habilitar cualquier cambio sobre el proyecto aceptado.
