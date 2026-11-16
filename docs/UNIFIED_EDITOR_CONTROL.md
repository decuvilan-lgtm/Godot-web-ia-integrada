# Control unificado del editor Godot

## Objetivo

Ofrecer a la IA una interfaz semántica y verificable para desarrollar juegos con comodidad: inspeccionar proyectos, modificar elementos del editor, ejecutar la vista previa, observar resultados, diagnosticar fallos y repetir pruebas.

La unificación consiste en **un contrato de capacidades y una política común de seguridad**, no en forzar un único transporte para plataformas incompatibles.

## Arquitectura elegida

| Capa | Godot Web | Editor nativo |
|---|---|---|
| Adaptador del editor | C++ integrado en el binario Web | EditorPlugin headless_session_bridge |
| Transporte | API de página + extensión Chromium | TCP local autenticado |
| Cliente/orquestación | semantic_controller.py y worker de Chromium | bridge_probe.gd / operador de sesión |
| Evidencia | Chromium, capturas, consola y vídeo del navegador | Captura de escritorio y vídeo del editor |
| Mutación | No habilitada en la primera versión | Operaciones allowlisted disponibles |
| Proyecto original | Solo lectura | Nunca se modifica directamente; usar sandbox |

### Por qué no se fusionan los dos adaptadores en un único plugin

Godot Web no ofrece el mismo conjunto de sockets, procesos ni capacidades del editor de escritorio. El agente Web está compilado dentro del motor y se comunica con el navegador. El puente nativo se ejecuta dentro del editor de escritorio y usa un socket TCP local.

Unificarlos en un único plugin de proyecto obligaría a instalar archivos en cada juego, rompería el aislamiento y no funcionaría igual en Web. Por eso se conserva un adaptador por entorno y se retira el antiguo addon Web instalado en proyectos, que duplicaba el adaptador integrado.

## Contratos actuales

### Godot Web — protocolo de página v1

La extensión transmite solicitudes al adaptador integrado. Comandos confirmados:

- editor.list_capabilities
- editor.get_state
- scene.get_tree

La lista se descubre mediante getCapabilities(). Las respuestas se correlacionan por ID. Las solicitudes y resultados están acotados; no se permite evaluación arbitraria, shell, acceso libre a archivos ni mutaciones genéricas.

### Editor nativo — protocolo TCP v1

El complemento publica un registro por proyecto con puerto, token aleatorio, PID, versión de protocolo e identidad del proyecto. El operador conecta exclusivamente a 127.0.0.1, autentica y envía solicitudes JSON delimitadas por línea.

El complemento valida token, versión, identidad del proyecto, tamaño y comandos permitidos. session_watcher.gd descubre el registro y mantiene heartbeats; bridge_probe.gd permite pruebas y operaciones controladas.

Las acciones nativas existentes incluyen inspección de escena y recursos, creación de nodos permitidos, configuración de algunas propiedades/colisiones, asignación de recursos visuales, Undo/Redo, apertura de escenas, foco del Inspector, vista previa y captura. La lista real se obtiene del adaptador; no asumir que todas las operaciones del editor están cubiertas.

## Vocabulario semántico común v1

Los clientes deben hablar en términos de intención, no de nombres internos del adaptador. El puente nativo ya expone esta primera capa de nombres canónicos; los nombres históricos se conservan como alias de compatibilidad mientras se migran los clientes.

| Comando canónico | Intención | Godot nativo | Godot Web |
|---|---|---|---|
| `editor.list_capabilities` | Descubrir funciones disponibles | Implementado | Implementado |
| `editor.get_state` | Estado del editor/proyecto | Implementado | Implementado |
| `scene.get_tree` | Inspeccionar escena activa | Implementado | Implementado |
| `scene.inspect_selection` | Inspeccionar selección | Implementado | Pendiente |
| `scene.add_node` / `scene.set_node_properties` | Crear nodos y cambiar propiedades permitidas con Undo | Implementado | Pendiente |
| `scene.configure_collision_shape` | Crear y configurar colisiones 2D | Implementado | Pendiente |
| `scene.assign_visual_resource` / `scene.create_sprite_frames` | Asignar texturas y crear recursos de animación | Implementado | Pendiente |
| `editor.open_scene` / `editor.focus_inspector` | Navegar escenas y enfocar Inspector | Implementado | Pendiente |
| `editor.inspect_undo_history` / `editor.undo` / `editor.redo` | Revisar y revertir cambios del puente | Implementado | Pendiente |
| `project.list_resources` / `project.inspect_resource` | Enumerar e inspeccionar recursos | Implementado | Pendiente |
| `preview.get_status` / `preview.start` / `preview.stop` | Consultar y controlar vista previa | Implementado | Pendiente |
| `capture.editor_screenshot` / `capture.desktop_screenshot` | Capturas del editor y escritorio | Implementado | Pendiente |
| `capture.start_editor_video` / `capture.stop_editor_video` / `capture.read_chunk` | Grabar vídeo y transferir evidencias | Implementado | Pendiente |

Cada adaptador publica su lista real de capacidades en tiempo de ejecución. "Pendiente" no debe simularse ni resolverse mediante clics o código arbitrario. Esta tabla describe el vocabulario y el estado comprobado, no promete paridad entre entornos.

## Reglas comunes

1. **Descubrir capacidades:** nunca inferir que una operación está disponible por el nombre del entorno.
2. **Identidad:** cada comando debe estar vinculado al proyecto, sesión y revisión correctos.
3. **Allowlist:** cada operación y argumento debe estar validado por esquema.
4. **Límites:** tamaños de mensaje, profundidad de árboles, número de nodos, tiempo de espera y solicitudes pendientes acotados.
5. **Mutación explícita:** leer antes de escribir; no guardar automáticamente ni reemplazar archivos ajenos.
6. **Undo/Redo:** cada modificación del editor debe ser recuperable cuando la API lo permita.
7. **Vista previa:** registrar inicio/parada y estado observado; no declarar que el juego reaccionó sin evidencia.
8. **Diagnóstico:** conservar el mensaje original, separar severidad del transporte y severidad declarada por Godot.
9. **Aislamiento:** trabajar en una copia desechable; publicar solo un diff revisado.
10. **Degradación clara:** devolver CAPABILITY_UNAVAILABLE o equivalente; no recurrir silenciosamente a coordenadas o código arbitrario.

## Límites actuales y trabajo pendiente

- Godot Web todavía es de solo lectura. Faltan selección, Inspector, navegación de escenas, edición segura y guardado.
- El editor nativo no cubre todos los recursos, scripts, señales, animaciones, TileMaps, importación, exportación, depuración y herramientas 3D.
- La vista previa nativa tiene ciclo básico de inicio/parada; faltan pausa/reanudación, consola estructurada de la instancia de juego, breakpoints y control integral del debugger.
- No existe todavía una única API de comandos de alto nivel compartida por ambos transportes. Los adaptadores tienen capacidades diferentes y deben anunciarlo. La futura capa común debe traducir operaciones semánticas sin mentir sobre las diferencias.
- El escaneo de carpetas del Project Manager Web puede ser síncrono y bloquear con árboles grandes; importar ZIP es la alternativa documentada hasta implementar escaneo incremental.

## Validación

Las pruebas deben ejecutarse por entorno:

- Python: validación del cliente semántico, loop de comandos y overlays.
- Godot Headless: importación y tests de contrato del complemento.
- Godot Editor real: proyecto nuevo desechable, edición, Undo/Redo, vista previa y capturas.
- Chromium: build Web reciente, comandos nativos de solo lectura, F6, consola y evidencias.
- Integridad: SHA del proyecto antes/después, diff y ausencia de archivos del controlador en el proyecto fuente.

No usar un juego privado o un repositorio ajeno como dependencia obligatoria de CI. Los tests de integración deben usar fixtures versionados dentro de este laboratorio.
