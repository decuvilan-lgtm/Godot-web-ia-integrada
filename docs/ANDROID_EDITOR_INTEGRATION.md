# Integración con el Godot Android modificado

**Estado de esta auditoría:** 2026-11-07. Revisión de repositorio, ramas, PR y ejecuciones de CI. No se modificó el repositorio del motor durante esta auditoría.

## Repositorio correcto

El editor Android al que se refiere el proyecto es:

- [Godot-engine4-v4.7.2-stable-difusion-modificado](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado)

Este repositorio no guarda el árbol completo del motor en cada commit de la rama principal. Sus workflows descargan Godot upstream 4.7.2-stable, aplican patchers versionados y compilan el editor. También mantiene snapshots del código modificado en el release documentado por su README. Por eso, las modificaciones persistentes deben entrar mediante patchers y validaciones reproducibles; no basta con cambiar el checkout temporal del workflow.

## Ramas y trabajo existente

La revisión de GitHub encontró estas líneas de trabajo:

| Rama | Estado observado | Contenido principal |
|---|---|---|
| `main` | Rama predeterminada | Flujo inicial de compilación y parche de importación GitHub pública |
| `feature/github-sync-and-safe-mcp` | PR #1 abierto, WIP | Sincronización incremental GitHub, MCP Android seguro, Terrain 3D y cambios de arranque |
| `feature/live-editor-link` | PR #2 abierto como borrador, basado en PR #1 | Live Link, relay WebSocket, cliente de agente, operaciones de archivos y escena |
| `feature/native-editor-integration` | Rama existente | Extensiones nativas y sincronización; requiere comparar antes de reutilizar |
| `work/mobile-ui-preflight` | Rama existente | Preflight de interfaz móvil |

No fusionar automáticamente PR #1 ni PR #2. Live Link depende de trabajo que todavía está en la rama base del PR #1.

## Evidencia CI observada para Live Link

En el último conjunto de ejecuciones consultado para el commit `2c2f380ba45cd05d08dd5ce0a5314bab4e7e1d20`:

- [Validación del relay Live Link, run 41388625597](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/actions/runs/41388625597): **success**. El job ejecutó pruebas del relay/operaciones y parseó el complemento con Godot 4.7.2.
- [Pipeline Android, run 41388625366](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/actions/runs/41388625366): **success global**, pero el job de compilación Android fue **skipped**; solo se ejecutó el preflight de integración. Esto no demuestra que se haya generado un APK.
- [Linux emitter, run 41388619849](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/actions/runs/41388619849): **failure** en el paso de compilación del editor Linux modificado. Hay que recuperar el log del job antes de corregirlo; el estado de CI por sí solo no revela la causa.

La bitácora de Live Link registra validaciones anteriores con Godot 4.7.2 headless y pruebas de operaciones de escena. Son evidencia útil de esos commits concretos, pero no sustituyen una prueba física en Android ni prueban el acceso desde ChatGPT cloud.

## Hallazgos de integración con Neon

El relay de la rama Live Link y el Neon Command Center creado para este proyecto todavía no comparten el mismo contrato de datos.

### 1. Autenticación duplicada

- `relay/server.py` valida el WebSocket con un único `LIVE_LINK_TOKEN` compartido.
- `relay/account_api.py` tiene un flujo separado de credenciales Bearer, dispositivos, tickets de enrolamiento y códigos de emparejamiento.
- El WebSocket no consume todavía la identidad autenticada de ese flujo de cuentas.

Por tanto, no se debe presentar el emparejamiento de cuentas como protección efectiva del WebSocket hasta unificar ambos caminos. El ID numérico del proyecto tampoco es una credencial.

### 2. Esquema de base de datos incompatible

El relay de Live Link espera tablas como `devices`, `enrollment_tickets`, `device_pair_codes`, `projects`, `project_members`, `project_revisions`, `project_files` y `project_changes`.

El proyecto Neon **Godot Command Center** tiene actualmente el esquema `command_center` con `workspaces`, `devices`, `pairing_codes`, `sessions`, `commands`, `command_results`, `revisions`, `snapshots`, `proposals`, `proposal_files` y `events`. No son esquemas equivalentes y las consultas actuales del relay no apuntan automáticamente a `command_center`.

No conectar el relay a la base de datos actual añadiendo solamente `DATABASE_URL`: primero hay que diseñar una migración/adaptador explícito y probarla contra el esquema real.

### 3. Identidad de proyecto incompatible

- El complemento Live Link usa un ID persistente de cuatro dígitos para identificar el proyecto en su UI/protocolo.
- La API de sincronización de archivos espera un UUID de proyecto en Postgres.

Se necesita una asociación explícita entre el ID visible local y el UUID interno. El ID de cuatro dígitos puede colisionar y no debe utilizarse como autorización.

### 4. Persistencia incompleta

- Las salas, sockets, operaciones pendientes y deduplicación del relay actual viven en memoria de proceso.
- Los reinicios eliminan ese estado.
- La API de sincronización guarda manifiestos/revisiones en Postgres, pero su documentación deja el adaptador de almacenamiento de blobs para una fase separada.
- Una transferencia de archivos no debe declararse persistida hasta que el contenido binario esté almacenado, verificado y recuperable.

Neon debe convertirse en fuente de verdad para identidad, revisiones, propuestas y operaciones durables. El WebSocket puede seguir transportando pantalla/entrada, pero no debe ser el único lugar donde existan cambios pendientes.

## Arquitectura recomendada

Mantener Live Link como integración principal con el editor Android modificado. No duplicarlo con otro complemento Android en el repositorio Godot Web IA.

1. **Android Godot modificado:** editor objetivo; presenta el ID local, valida el proyecto, solicita aprobación y aplica cambios mediante el historial Undo/Redo cuando corresponda.
2. **Godot Web / workspace del agente:** entorno aislado donde el agente inspecciona y prepara cambios. Nunca sobrescribe el proyecto aceptado directamente.
3. **Neon Command Center:** identidad, dispositivos, autorización, sesiones, cola durable, revisiones, snapshots, propuestas y eventos.
4. **Relay Render Free:** transporte WSS y señalización en tiempo real. Su memoria es efímera; la cola y el estado autoritativo residen en Neon. Mantener el servicio en plan gratuito y no crear recursos pagos.
5. **Agente externo:** cliente que habla el protocolo Live Link y solo ejecuta operaciones autorizadas. Un protocolo WebSocket no equivale a una API de inferencia; pero ChatGPT necesita una herramienta/conector compatible para iniciar operaciones. No prometer acceso directo desde esta conversación hasta demostrarlo.

## Siguiente secuencia de implementación

1. Comparar PR #1, PR #2 y `feature/native-editor-integration`; elegir una base sin perder cambios existentes.
2. Obtener los logs completos del fallo del Linux emitter y corregirlo en una rama de trabajo, no en `main`.
3. Especificar un único contrato de identidad: cuenta/dispositivo autenticado + UUID interno + ID corto visible.
4. Adaptar el modelo Neon `command_center` al flujo real de Live Link mediante migraciones aditivas; no crear una segunda base ni borrar datos existentes.
5. Hacer que el WebSocket autentique cada conexión contra el dispositivo emparejado y autorice el proyecto/rol. Eliminar el token global compartido como mecanismo de autorización de producción.
6. Persistir operaciones, ACK, revisiones y resultados; hacer que la reconexión reanude desde un cursor durable.
7. Completar almacenamiento de blobs con hashes, límites, staging y recuperación; preservar diffs y snapshots antes de aplicar cambios.
8. Ejecutar pruebas automatizadas de relay, autenticación, concurrencia, duplicados, reinicio y conflicto de revisión.
9. Ejecutar build Android ARM32/ARM64 y pruebas reales de instalación, apertura del editor, aprobación y actualización de un proyecto en el teléfono.
10. Solo entonces evaluar el mecanismo compatible para que ChatGPT opere el agente. No declarar Live Link terminado por tener CI verde en pruebas de protocolo.

## Límites y reglas

- No fusionar borradores ni publicar un APK sin autorización y sin pruebas correspondientes.
- No usar el ID corto como secreto.
- No enviar tokens a GitHub, archivos de proyecto ni logs.
- No reemplazar el editor Android por una app espejo.
- No sincronizar archivos destructivamente sin base revision, diff, respaldo y confirmación.
- No activar infraestructura paga ni cambiar los servicios Render del plan Free.
- Diferenciar siempre entre comprobación estática, prueba headless, compilación, instalación y uso real en el dispositivo.


## Godot editor-side Command Center client

The Android editor branch PR #3 now includes an experimental client in the existing Live Link addon:

- [Addon implementation](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/blob/feature/neon-command-center-adapter/scripts/live_link_addon/plugin.gd)
- [Addon integration notes](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/blob/feature/neon-command-center-adapter/scripts/live_link_addon/README.md)

The client uses HTTPS, pairs with a single-use code, receives its authoritative device role from the server, polls the durable command queue, and acknowledges results. Its first command executor is restricted to `ping`, `project.get_state`, `project.list_files`, `scene.inspect`, and `script.read`. It does not write project files, run shell commands, simulate input or edit scenes. Script reads are limited to 64 KiB; file listings are bounded and omit common secret-file patterns and generated folders.

The bearer credential stays in memory only. A random installation identifier is stored in editor settings, and presenting a new administrator-issued pairing code for that installation rotates its device credential instead of creating a duplicate device record. Persistent secure credential storage still requires platform-specific Android Keystore/Web Crypto work.

**This is not yet operational end-to-end:** the Render relay has not been configured with the Neon database/admin secrets, there is no web UI to issue pairing codes, and no Android physical-device test has been run. The WebSocket Live Link still uses its legacy room/token authentication; the new queue is a separate HTTP channel.

## Actual implementation progress — Neon queue adapter

A new isolated branch was created in the Android editor repository:

- [PR #3 — durable Neon Command Center API adapter](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/pull/3)
- [API adapter source](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/blob/feature/neon-command-center-adapter/relay/command_center_api.py)
- [Agent-side HTTP client](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/blob/feature/neon-command-center-adapter/relay/command_center_client.py)
- [Adapter and environment documentation](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/blob/feature/neon-command-center-adapter/docs/NEON_COMMAND_CENTER_API.md)

The adapter uses the existing `command_center` schema and supports workspace-scoped single-use pairing, hashed device credentials, a persistent read-only command queue, leases/recovery, result storage, and strict browser CORS for the web editor. The agent client requires HTTPS remotely and requires idempotency keys for command creation.

Migration `002_live_link_command_leases.sql and 003_require_command_idempotency_keys.sql` was applied to the Neon production branch and its columns, constraints and indexes were verified. The database still has one workspace and zero paired devices or queued commands.

**CI evidence:** the relay test suite, agent-client tests, and Godot 4.7.2 headless Live Link/filesystem harness passed. The latest branch-head validation is [42340748683](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/actions/runs/42340748683), which passed. The Linux emitter build is a separate manual workflow and was not run by this PR validation.

**Not deployed:** no Render environment variables or deployment were changed. The API has not been configured with `COMMAND_CENTER_DATABASE_URL` or `COMMAND_CENTER_ADMIN_TOKEN`; no devices have been paired; editor-side polling is not connected; the existing Live Link WebSocket still uses its legacy authentication. This is a tested code foundation, not end-to-end Android/Web synchronization.
