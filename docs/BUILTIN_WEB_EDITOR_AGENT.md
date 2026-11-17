# Built-in Godot Web Agent Adapter

## Decisión

El adaptador está integrado en el binario del editor Godot Web. No se instala un addon en los proyectos importados, no modifica project.godot y no altera el ZIP del juego.

## Punto de integración

La implementación parchea el WebToolsEditorPlugin de Godot 4.7.2-stable en los archivos del motor Web. El parche es anchor-validated y falla si el código upstream ya no coincide con las ubicaciones esperadas.

Archivos del motor modificados por el patcher de producción:
- platform/web/editor/web_tools_editor_plugin.h
- platform/web/editor/web_tools_editor_plugin.cpp
- editor/project_manager/project_list.cpp
- editor/debugger/editor_debugger_server.cpp
- platform/web/audio_driver_web.cpp
- editor/debugger/debug_adapter/debug_adapter_server.cpp

El adaptador recibe solicitudes en una cola acotada y procesa las operaciones desde el hilo del editor. La interfaz de página es window.__godotEditorAgent.

## Comandos Web disponibles

- `editor.list_capabilities`
- `editor.get_state`
- `scene.get_tree` (máximo 256 nodos y 16 niveles; rutas relativas a la raíz de la escena)
- `scene.inspect_node` (hasta 80 propiedades del Inspector, solo lectura, para una ruta relativa validada)
- `scene.add_node` (creación de un nodo con clase allowlisted, nombre validado y padre dentro de la escena activa)

`scene.add_node` usa `EditorUndoRedoManager`, queda disponible para deshacer y no guarda la escena automáticamente. La lista permitida incluye nodos comunes 2D/Control, no clases arbitrarias. No hay ejecución arbitraria de GDScript, shell, procesos ni acceso libre al filesystem. La edición general de propiedades, scripts y recursos sigue pendiente.

## Compatibilidad Web

El patcher:
- Evita esperar un hilo de escaneo que no se pudo iniciar en el runtime Web; utiliza el camino síncrono compatible para el Project Manager.
- Comprueba que los hilos de audio solo se esperen si se iniciaron.
- Evita iniciar el servidor Debug Adapter TCP externo en Web, donde no hay sockets TCP nativos.
- Mantiene registrado el factory TCP del debugger para evitar una ruta nula en el código que consulta el protocolo; la disponibilidad real del servidor debe tratarse como no soportada en Web.

El escaneo síncrono del Project Manager puede bloquear la interfaz con directorios muy grandes. Importar un ZIP es la alternativa actual.

## Compilación y aceptación

- .github/workflows/build-godot-web-agent-editor.yml compila el editor personalizado.
- scripts/build/patch_godot_web_agent.py aplica el parche.
- tests/test_web_agent_patcher.py comprueba anchors, allowlist y protecciones de hilos.
- scripts/build/smoke_test_godot_web_agent.py valida el binario en Chromium.
- .github/workflows/browser-smoke-reuse.yml permite repetir la aceptación indicando un artefacto de compilación concreto.

No usar artefactos antiguos como evidencia de la rama actual. Para aceptar un cambio, comprobar la compilación, la prueba Chromium y las comprobaciones del repositorio del mismo SHA.

## Estado

La versión actual combina inspección con una primera mutación acotada: crear nodos mediante `scene.add_node`. No es todavía un editor autónomo completo; editar propiedades, recursos y scripts desde Chromium sigue pendiente. No se necesita una PC ni un agente local para esta ruta: la ampliación de edición debe seguir dentro del binario Godot Web que ejecuta GitHub Actions. El puente nativo es una herramienta experimental separada, no un requisito del flujo móvil.
