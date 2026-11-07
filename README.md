# Godot Web IA Integrada

Entorno de desarrollo con dos puestos de trabajo que comparten un mismo proyecto sin pisarse:

- **Puesto de la IA:** editor real Godot Web publicado en Render. El agente trabaja sobre un workspace aislado.
- **Puesto del usuario:** Godot Editor para Android, construido desde el motor que está fijado en este mismo repositorio bajo `engine/godot`. El usuario conserva el control del proyecto aceptado desde su teléfono.
- **Centro de mando:** Neon Postgres conserva sesiones, dispositivos, órdenes, resultados, revisiones, snapshots y propuestas. Neon Realtime se usa como canal de notificaciones; Postgres sigue siendo la fuente de verdad.

La regla central es que el agente nunca sobrescribe directamente el proyecto aceptado en Android. Sus cambios se presentan como propuestas con diff, validación y snapshot; solo se aplican tras aprobación explícita.

> **Estado real:** editor web 4.7.2-stable publicado; AI Bridge de solo lectura; relay HTTP/WebSocket existente; esquema persistente de Neon instalado y documentado. Todavía no existe emparejamiento Android/Web de extremo a extremo ni escritura remota habilitada.

## Acceso

- Editor web de la IA: https://godot-web-ia-integrada-rt2l.onrender.com
- Relay: https://godot-web-ia-relay.onrender.com
- Salud del relay: https://godot-web-ia-relay.onrender.com/health
- [Repositorio GitHub](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada)
- [Centro de mando Neon](https://console.neon.tech/app/projects/aged-dew-94732514)

**Infraestructura:** los servicios Render existentes están configurados en plan `free`. No crear ni cambiar recursos a planes pagos. El relay puede suspenderse y reiniciarse; por eso no se considera almacenamiento persistente.

## Godot Android y motor

El motor oficial está fijado como submódulo en `engine/godot`, versión/tag **4.7.2-stable**. El árbol de código incluye la plataforma Android del motor; no se reemplaza por un proyecto de ejemplo ni por otro editor. La distribución web inicial utiliza el paquete oficial precompilado.

- Motor: https://github.com/godotengine/godot
- Submódulo: `engine/godot`
- Versión fijada: `4.7.2-stable`

## Qué está implementado

### Editor web
- Distribución oficial Godot Web.
- Build que verifica SHA-256 del paquete.
- Encabezados COOP/COEP.
- Proyecto sandbox para probar el complemento.

### AI Bridge v0.1
Conexión WebSocket segura y token temporal en memoria. Acciones disponibles:
- `ping`
- `project.get_state`
- `project.list_files`
- `scene.inspect`
- `script.read`

No habilita escritura arbitraria, shell ni ejecución de procesos.

### Relay v0.1
- FastAPI/Uvicorn en Render Free.
- Sesiones efímeras, credenciales separadas y WebSocket.
- Reenvío de solicitudes al editor conectado.
- No almacena proyectos ni archivos.

### Neon Command Center — base persistente inicial
El proyecto Neon se llama **Godot Command Center**. El esquema `command_center` ya está instalado en `neondb` e incluye workspaces, devices, sessions, commands, command_results, revisions, snapshots, proposals, proposal_files y events. Se creó el workspace `default`.

- [Diseño y estado del centro de mando](docs/COMMAND_CENTER.md)
- [Migración SQL](database/migrations/001_command_center.sql)

Neon Realtime está habilitado para el origen del editor web. Esto aún no constituye una API ni sincronización operativa: falta desplegar el servicio autenticado que lea/escriba la cola y gestione el ciclo de vida de dispositivos.

## Próximas etapas

1. API autenticada y worker persistente sobre Neon.
2. Emparejamiento de un solo uso y registro de Android, editor web y controlador IA.
3. Conexión del AI Bridge a la cola durable, con reconexión por cursor.
4. Integración Android mediante exportación/importación versionada, sin tocar archivos locales sin aprobación.
5. Propuestas, diffs, validación, snapshots y rollback.
6. Runner aislado, logs y capturas reales.
7. Pruebas de desconexión, duplicados, conflictos de revisión y suspensión de Render.

## Desarrollo

- [Arquitectura técnica](docs/ARCHITECTURE.md)
- [Centro de mando](docs/COMMAND_CENTER.md)
- [Protocolo del puente](docs/BRIDGE_PROTOCOL.md)
- [Relay](relay/README.md)
- [Complemento AI Bridge](examples/bridge-sandbox/addons/godot_ai_bridge/plugin.gd)
