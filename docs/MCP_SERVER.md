# Godot MCP Server

## Endpoint

`https://godot-web-ia-relay.onrender.com/mcp`

Transporte: MCP Streamable HTTP. El servicio se monta dentro del Relay FastAPI y comparte el ciclo de vida del proceso y el pool Neon. El endpoint está protegido por un middleware de autenticación de dispositivos.

## Autenticación

Enviar en cada petición MCP:

`Authorization: Bearer <device_credential>`

La credencial debe pertenecer a un dispositivo emparejado con rol `agent_controller`. Se comprueba el hash contra `command_center.devices` en Neon en cada petición. Credenciales revocadas, inexistentes o de rol editor reciben rechazo antes de que se ejecute una herramienta.

La credencial se obtiene mediante el flujo normal de emparejamiento de dispositivos. El código temporal caduca en 120 segundos y solo se muestra una vez. No guardarlo en el repositorio, en el proyecto Godot, en logs ni en conversaciones.

## Herramientas expuestas

| Herramienta | Función |
|---|---|
| `godot_workspace_status` | Lista los dispositivos emparejados del workspace autenticado y sus últimas conexiones. |
| `godot_enqueue_command` | Encola una orden idempotente para el editor Web aislado. |
| `godot_command_status` | Devuelve estado, resultado y error de una orden del mismo workspace. |
| `godot_list_recent_commands` | Lista resúmenes de hasta 50 órdenes recientes. |
| `godot_start_task` | Inicia una tarea Godot allowlisted; CircleCI es el proveedor primario y GitHub Actions el respaldo. |
| `godot_task_status` | Consulta el estado de una ejecución CircleCI o GitHub Actions. |

### Encolar una orden

`godot_enqueue_command` recibe:

- `action`: nombre de la acción.
- `args`: objeto JSON con argumentos validados por el contrato del Command Center.
- `idempotency_key`: clave estable para reintentar la misma solicitud sin duplicarla.

El destino está fijado a `web_editor`; el cliente no puede redirigir órdenes al editor Android ni escoger otro workspace. Para consultar el resultado, usar el `command_id` devuelto con `godot_command_status`.

## Política de comandos

Permitidos:

- `ping`
- `project.get_state`
- `project.list_files`
- `scene.inspect`
- `script.read`
- `visual.capture` para `editor_2d` o `editor_3d`
- `visual.capture_sequence` para `editor_2d` o `editor_3d`

No permitidos:

- Escritura o eliminación de archivos y scripts.
- Shell o ejecución arbitraria de procesos.
- Operaciones sobre el proyecto Android desde MCP.
- `visual.zoom_to`, captura `editor_ui` o `game_preview`.
- WebP y hojas de contacto no soportadas por el backend actual.

MCP y REST comparten las mismas tablas, política visual, expiración e idempotencia. No hay una segunda cola.

## Estado de integración

El código del servidor está en `relay/mcp_server.py`; el endpoint se monta desde `relay/app.py`. El commit `48034bc16e8f9337fd5fffb85c54f705d2e1996e` pasó CI. El despliegue de Render debe verificarse por separado.

Un endpoint MCP desplegado no queda automáticamente disponible como herramienta dentro de ChatGPT. Hace falta registrar/configurar el servidor en un host MCP compatible y emparejar un `agent_controller`. Hasta que esa integración se pruebe, no afirmar que ChatGPT ya puede invocar el endpoint directamente.


## Ejecución remota directa

Las tareas de validación no esperan a que el editor web esté abierto. El Relay invoca al proveedor CI directamente, en este orden:

1. CircleCI (principal).
2. GitHub Actions (respaldo cuando CircleCI no está configurado o no responde).

Los perfiles disponibles son `engine_smoke` y `scene_audit_3d`. Ambos ejecutan un binario oficial Godot 4.7.2 verificado por SHA-512. No se aceptan comandos de shell, rutas ni ramas arbitrarias desde MCP. Consulta [REMOTE_EXECUTION.md](REMOTE_EXECUTION.md) para configuración, límites gratuitos y alcance de las pruebas 3D.
