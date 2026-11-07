# Godot Web IA Integrada

Entorno de desarrollo con dos puestos de trabajo que comparten un mismo proyecto sin pisarse:

- **Puesto de la IA:** editor real Godot Web publicado en Render. El agente trabaja sobre un workspace aislado.
- **Puesto del usuario:** tu editor Godot para Android, basado en el trabajo del repositorio [Godot-engine4-v4.7.2-stable-difusion-modificado](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado). Ese repositorio conserva el parche y el flujo reproducible que reconstruye el APK sobre Godot 4.7.2.
- **Centro de mando:** Neon Postgres conserva sesiones, dispositivos, órdenes, resultados, revisiones, snapshots y propuestas. Neon Realtime se usa como canal de notificaciones; Postgres sigue siendo la fuente de verdad.

La regla central es que el agente nunca sobrescribe directamente el proyecto aceptado en Android. Sus cambios se presentan como propuestas con diff, validación y snapshot; solo se aplican tras aprobación explícita.

> **Estado real:** editor web 4.7.2-stable publicado; AI Bridge de solo lectura; relay HTTP/WebSocket existente; esquema persistente de Neon instalado y documentado. Todavía no existe emparejamiento Android/Web de extremo a extremo ni escritura remota habilitada.

## Acceso

- Editor web de la IA: https://godot-web-ia-integrada-rt2l.onrender.com
- Relay: https://godot-web-ia-relay.onrender.com
- Salud del relay: https://godot-web-ia-relay.onrender.com/health
- [Repositorio de integración IA](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada)
- [Repositorio Godot Android modificado](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado)
- [Centro de mando Neon](https://console.neon.tech/app/projects/aged-dew-94732514)

**Infraestructura:** los servicios Render existentes están configurados en plan `free`. No crear ni cambiar recursos a planes pagos. El relay puede suspenderse y reiniciarse; por eso no se considera almacenamiento persistente.

## Godot Android: fuente correcta

El repositorio que debemos tomar como referencia para el editor Android es **Godot-engine4-v4.7.2-stable-difusion-modificado**, no el submódulo genérico de este repositorio de integración.

Importante: ese repositorio no almacena el árbol completo del motor. Su README indica que el workflow descarga temporalmente `godotengine/godot` en el tag `4.7.2-stable`, aplica el parche mantenido en `scripts/apply_github_import_patch.py` y compila el APK Android. El código modificado persistente está, por ahora, representado por ese parche y sus workflows. Por tanto, cualquier integración nativa de IA debe incorporarse como cambios reproducibles al parche/build de ese repositorio, no editar una copia efímera del motor ni asumir que el submódulo de aquí contiene las modificaciones del usuario.

- [Repositorio y documentación del editor Android](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado)
- [Parche actual del Project Manager](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/blob/main/scripts/apply_github_import_patch.py)
- [Workflow de compilación Android](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/blob/main/.github/workflows/build-godot-android-source.yml)

El submódulo `engine/godot` que existe en este repositorio de integración es una referencia upstream fijada a 4.7.2-stable; no debe confundirse con el flujo modificado del editor Android.

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
4. Integración en el repositorio Godot Android modificado: primero lectura/diagnóstico y luego intercambio de propuestas versionadas, sin tocar archivos locales sin aprobación.
5. Propuestas, diffs, validación, snapshots y rollback.
6. Runner aislado, logs y capturas reales.
7. Pruebas de desconexión, duplicados, conflictos de revisión y suspensión de Render.

## Desarrollo

- [Auditoría e integración con el Godot Android modificado](docs/ANDROID_EDITOR_INTEGRATION.md)
- [Arquitectura técnica](docs/ARCHITECTURE.md)
- [Centro de mando](docs/COMMAND_CENTER.md)
- [Protocolo del puente](docs/BRIDGE_PROTOCOL.md)
- [Relay](relay/README.md)
- [Complemento AI Bridge](examples/bridge-sandbox/addons/godot_ai_bridge/plugin.gd)
