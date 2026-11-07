# Arquitectura técnica

## Centro de mando persistente (Neon)

El proyecto Neon **Godot Command Center** está en la región `aws-us-east-2`, compatible con Neon Functions. El esquema `command_center` ya existe en `neondb`: workspaces, devices, pairing_codes, sessions, commands, command_results, revisions, snapshots, proposals, proposal_files y events. Hay un workspace inicial `default`. Neon Realtime está habilitado para el origen del editor web.

La migración reproducible está en `database/migrations/001_command_center.sql`; el diseño y sus invariantes están en `docs/COMMAND_CENTER.md`.

**Límite actual:** todavía no hay Neon Function/API desplegada ni dispositivos emparejados. La persistencia de tablas no significa que el relay actual ya las use. El relay sigue manteniendo sesiones y solicitudes en memoria hasta completar la migración y las pruebas. No habilitar escritura remota basándose únicamente en que las tablas existan.

## Dos puestos de trabajo

La web Godot Web no es la herramienta principal del usuario: es el puesto remoto del agente. El usuario trabaja en Godot Editor para Android, cuyo motor fuente está fijado como submódulo en `engine/godot` (4.7.2-stable), incluyendo la plataforma Android. El objetivo es que ambos puedan observar el mismo proyecto y que el agente pueda proponer cambios sin sobrescribir trabajo aceptado.

## Estado implementado

### 1. Editor Web de la IA
- Distribución oficial Godot Web 4.7.2-stable.
- Build descarga el paquete oficial y verifica SHA-256.
- Render static site.
- Metadatos viewport y encabezados COOP/COEP.

### 2. AI Bridge v0.1
Complemento `EditorPlugin` con dock de conexión WebSocket. El usuario/editor configura una URL `wss://` y un token temporal guardado solo en memoria.

Acciones de solo lectura:
- `ping`
- `project.get_state`
- `project.list_files`
- `scene.inspect`
- `script.read`

Límites: 1000 rutas, 500 nodos, profundidad 32, archivos de texto de 256 KiB, solo `res://` y extensiones permitidas. No hay escritura arbitraria ni ejecución de shell.

### 3. Relay v0.1
Servicio Python/FastAPI separado, desplegado en Render con plan `free`.
- `GET /health`
- `POST /v1/sessions` autenticado por `X-Admin-Token`
- `GET /v1/sessions/{id}` con token de controlador
- `POST /v1/sessions/{id}/request` para enviar solicitudes al editor conectado
- `wss://.../v1/editor/{id}` para el complemento

Sesiones en memoria, expiración predeterminada de 30 minutos, sin persistencia de proyectos. Un reinicio invalida sesiones. El relay aún requiere prueba de integración y un controlador que el agente pueda invocar directamente.

## Arquitectura objetivo

### 4. Workspace y versiones
Estados separados:
- **User workspace**: proyecto aceptado del usuario en Godot Android.
- **Agent workspace**: copia remota donde trabaja el agente en el editor web.
- **Proposal**: diff revisable entre ambos.
- **Snapshot**: punto de restauración previo a aplicar cambios.

El trabajo experimental del agente nunca debe borrar el proyecto aceptado del usuario. Sincronización con IDs estables, versionado, detección de conflictos y recuperación ante desconexión.

### 5. Edición segura
Futuras acciones:
- crear/actualizar nodos y propiedades permitidas;
- leer y parchear scripts con diff;
- inspeccionar recursos y referencias;
- validar cambios antes de aplicarlos;
- snapshot previo y rollback.

No se habilitará escritura general de archivos hasta probar validación y recuperación.

### 6. Runner y observación
Runner aislado para ejecutar proyectos y devolver:
- versión del motor y configuración;
- logs y código de salida;
- capturas reales antes/después;
- duración y recursos usados.

El observador podrá ver la interfaz completa o solo el viewport. No se aceptarán capturas simuladas como evidencia.

### 7. Sincronización con Android
El usuario abre el proyecto en Godot Android. El agente trabaja sobre una copia remota; los cambios se intercambian mediante paquetes/diffs y se aplican al proyecto del usuario solo tras aprobación. La primera integración puede usar exportación/importación de paquetes versionados antes de intentar sincronización en vivo.

## Fuente del motor y parches

El submódulo `engine/godot` fija el commit exacto de `4.7.2-stable`. Los cambios propios del motor se guardan como parches versionados y se aplican sobre una copia de trabajo, sin modificar upstream.

## Próximas fases

1. Editor web remoto para la IA: desplegado; falta validación visual y funcional completa.
2. Bridge de solo lectura: implementado; falta prueba con relay real.
3. Relay gratuito: creado con plan free; falta prueba de integración y acceso directo desde el controlador IA.
4. Workspace y sincronización con Android.
5. Edición segura mediante diffs y snapshots.
6. Runner, logs y capturas.
7. Integración nativa del motor solo si las extensiones no alcanzan.

## Riesgos
- Suspensión e inactividad del plan gratuito.
- Pérdida de sesiones en reinicios.
- Memoria y cuotas del navegador Android.
- Persistencia y conflictos de archivos.
- Capacidades no disponibles en editor web frente al nativo.
- Compatibilidad del plugin con la versión Android exacta del editor.
