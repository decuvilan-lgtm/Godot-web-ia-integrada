# Arquitectura técnica

## Principio central

La IA debe operar el editor Godot real mediante operaciones estructuradas, no mediante clicks ciegos como mecanismo principal. El control visual será complementario. Los cambios se proponen primero en un espacio de trabajo separado y no alteran el proyecto aceptado hasta que se aprueban.

## Estado implementado

### 1. Editor Web
- Distribución oficial Godot Web 4.7.2-stable.
- El build descarga el paquete oficial y comprueba su SHA-256.
- Render sirve el resultado como sitio estático gratuito.
- El HTML recibe metadatos de viewport móvil.
- El sitio declara COOP/COEP para los requisitos de aislamiento de origen del editor.

Esto valida el empaquetado y publicación; no demuestra todavía compatibilidad completa con todos los navegadores Android ni persistencia tras cerrar la pestaña.

### 2. AI Bridge v0.1: complemento de solo lectura

Ubicación: `examples/bridge-sandbox/addons/godot_ai_bridge`.

Es un `EditorPlugin` con un dock de conexión. El usuario introduce una URL `wss://` y un token temporal. El token no se guarda en el proyecto ni en disco. El complemento usa `WebSocketPeer` y autentica antes de atender solicitudes.

Acciones habilitadas:
- `ping`
- `project.get_state`
- `project.list_files`
- `scene.inspect`
- `script.read`

Límites defensivos:
- Máximo 1000 archivos listados.
- Máximo 500 nodos por árbol y profundidad 32.
- Máximo 256 KiB por archivo leído.
- Solo rutas `res://` sin segmentos de traversal.
- Solo extensiones de texto permitidas.
- No existe ejecución arbitraria de shell.
- Cualquier acción desconocida se rechaza.

El complemento es funcional como cliente de protocolo, pero no puede conectarse hasta que exista un servidor relay compatible.

## Componentes pendientes

### 3. Relay y sesiones
Servidor WebSocket/HTTP para emparejar el editor con el agente, autenticar ambos extremos, mantener solicitudes correlacionadas y gestionar reconexiones. El servidor debe validar origen, límites de tamaño, frecuencia y expiración de sesión.

### 4. Workspace y versiones
Estados separados:
- **User workspace**: estado aceptado del proyecto.
- **Agent workspace**: copia de trabajo del agente.
- **Proposal**: diff revisable entre ambos.
- **Snapshot**: punto de restauración anterior a cambios aplicados.

Borrar o revertir contenido en el workspace del agente nunca debe borrar cambios aceptados del usuario. El almacenamiento del navegador no será la única copia.

### 5. Edición segura
Acciones futuras:
- crear/actualizar nodos y propiedades permitidas;
- leer y parchear scripts con diff;
- inspeccionar recursos;
- validar referencias antes de aplicar;
- snapshot previo y rollback.

No se habilitarán escrituras generales de archivos hasta tener validación, permisos y recuperación probados.

### 6. Runner y observación
Un runner aislado deberá registrar:
- versión del motor y configuración;
- operación ejecutada y código de salida;
- logs relevantes;
- capturas reales antes/después;
- duración y recursos usados.

El observador debe capturar la interfaz completa o solo el viewport. No se aceptarán imágenes simuladas como evidencia de una prueba.

### 7. Sincronización
Identidad estable del proyecto, historial de cambios, sincronización incremental, detección de conflictos y recuperación ante desconexión móvil.

## Fuente del motor y parches

El submódulo `engine/godot` apunta al commit exacto del tag `4.7.2-stable`. No se modifica el repositorio upstream. Los cambios propios del motor se guardarán como parches versionados en `patches/godot/` y se aplicarán sobre una copia de trabajo del submódulo.

## Próximas fases

1. **Bootstrap web**: completado; falta probar visualmente en Android real.
2. **Bridge mínimo**: cliente de solo lectura implementado; falta el relay.
3. **Relay gratuito de pruebas**: implementar y planificar como recurso independiente, sin aceptar planes de pago.
4. **Edición segura**: diffs, snapshots y operaciones limitadas.
5. **Runner**: pruebas aisladas, logs y capturas.
6. **Sesión compartida**: el agente opera el workspace remoto y el usuario observa los mismos cambios desde Android.
7. **Integración nativa**: modificar Godot solo cuando una extensión no alcance.

## Riesgos a validar

- Requisitos COOP/COEP y SharedArrayBuffer.
- Límites de memoria y compatibilidad del navegador Android.
- Persistencia del proyecto al cerrar pestaña o perder conexión.
- Compatibilidad de IndexedDB y cuota de almacenamiento.
- Capacidades que la compilación web no ofrece frente al editor nativo.
- Tiempo de carga inicial y caché.
- Suspensión por inactividad y almacenamiento efímero de cualquier backend gratuito.
