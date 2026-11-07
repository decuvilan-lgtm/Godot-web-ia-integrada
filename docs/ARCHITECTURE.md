# Arquitectura técnica

## Principio central

La IA no controla el editor mediante clicks ciegos como mecanismo principal. El editor sigue siendo Godot real; el puente expone una API estructurada, observable y limitada. La automatización visual queda como recurso complementario para acciones que no tengan una API estable.

## Componentes

### 1. Editor Web

- Distribución web oficial fijada por versión y checksum.
- Carga desde el navegador sin instalar herramientas en el teléfono.
- En Android: diseño de página adaptable, paneles plegables y controles táctiles.
- El editor y los proyectos no se mezclan con el panel de automatización.

### 2. AI Bridge

Contrato versionado, inicialmente sobre WebSocket/HTTP:
- `project.get_state`
- `project.list_files`
- `scene.inspect`
- `scene.get_node_tree`
- `scene.create_node`
- `scene.update_node`
- `script.read`
- `script.patch`
- `resource.inspect`
- `test.run`
- `editor.capture`
- `workspace.snapshot`
- `workspace.diff`
- `workspace.apply`

No se expondrá un endpoint de ejecución arbitraria de shell al navegador. Los trabajos de compilación y pruebas se ejecutarán en un runner aislado con lista permitida de operaciones.

### 3. Workspace y versiones

Estados separados:
- **User workspace**: estado aceptado del proyecto.
- **Agent workspace**: copia de trabajo del agente.
- **Proposal**: diff revisable entre ambos.
- **Snapshot**: punto de restauración anterior a cambios aplicados.

Borrar o revertir contenido en el workspace del agente nunca debe borrar cambios aceptados del usuario.

### 4. Observación y pruebas

Cada prueba debe registrar:
- versión del motor y configuración;
- comando/operación de prueba;
- resultado y código de salida;
- logs relevantes;
- capturas antes/después cuando corresponda;
- duración y recursos usados.

El observador debe poder solicitar capturas de la interfaz completa o solo del viewport del proyecto. Las capturas deben corresponder a la sesión real, no a una imagen simulada.

### 5. Sincronización

El proyecto debe tener una identidad estable y un historial de cambios. La sincronización será incremental, con detección de conflictos y recuperación ante desconexión móvil. No se dependerá del almacenamiento temporal del navegador como única copia.

## Fuente del motor y parches

El submódulo `engine/godot` apunta al commit exacto del tag `4.7.2-stable`. No se modifica el repositorio upstream. Los cambios propios del motor se guardarán como parches versionados en `patches/godot/` y se aplicarán sobre una copia de trabajo del submódulo. Esto facilita revisar, retirar y rebasar cambios cuando se actualice Godot.

## Fases

1. **Bootstrap web**: publicar y abrir el editor oficial en Render.
2. **Inspección**: detectar capacidades del editor web y validar persistencia de proyectos.
3. **Bridge mínimo**: conexión autenticada, estado del editor y lectura del proyecto.
4. **Edición segura**: operaciones de escena/script, diffs y snapshots.
5. **Runner**: pruebas aisladas, logs y capturas.
6. **Sesión compartida**: el agente opera el workspace remoto y el usuario ve los mismos cambios desde Android.
7. **Integración nativa**: parchear el código fuente de Godot solo donde el puente no pueda resolverse como extensión web.

## Riesgos a validar

- Requisitos de aislamiento de origen (COOP/COEP) y SharedArrayBuffer.
- Límites de memoria y compatibilidad del navegador Android.
- Persistencia del proyecto al cerrar pestaña o perder conexión.
- Compatibilidad de IndexedDB y cuota de almacenamiento.
- Capacidades que la compilación web no ofrece frente al editor nativo.
- Tiempo de carga del paquete inicial y caché de recursos.
