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
- `scene.inspect_node` (hasta 80 propiedades del Inspector para una ruta relativa validada)
- `scene.add_node` (crea nodos de una lista acotada de clases 2D, físicas, animación, audio y UI)
- `scene.set_property` (cambia una propiedad visible y editable del Inspector con conversión tipada)

`scene.set_property` admite valores escalares, vectores 2D/3D, colores, NodePath/StringName y referencias a recursos existentes mediante `{"resource_path":"res://..."}`. Las referencias se limitan al proyecto importado y el tipo de recurso debe coincidir con el tipo declarado por Godot. No permite rutas externas ni valores JSON anidados arbitrarios.

Todas las mutaciones usan `EditorUndoRedoManager`, quedan disponibles para deshacer y no guardan la escena automáticamente. El flujo `semantic-build` de B puede crear hasta 12 nodos, configurar hasta 12 propiedades por nodo y verificar tanto el árbol como la lectura posterior del Inspector. La creación sigue limitada a clases allowlisted; no se instancian clases arbitrarias.

## Vista previa del juego

B puede:
- Ejecutar la escena con F6 (`run_game`).
- Cambiar a la pestaña Game y detectar el canvas real (`game_view`).
- Hacer clic en coordenadas normalizadas dentro del canvas (`game_click`).
- Mantener teclas permitidas durante 50-5000 ms, con liberación garantizada (`game_input`).
- Capturar la vista previa como JPEG inline mientras A mantiene la misma sesión de Chromium.

La entrada de juego es distinta de las operaciones semánticas del editor. No se usa como método para construir escenas. Las capturas PNG completas y el registro de comandos quedan en el artefacto de Workflow A.

No hay ejecución arbitraria de GDScript, shell, procesos ni acceso libre al filesystem. La asignación de recursos existentes está acotada a referencias `res://`; la creación o edición arbitraria de scripts no se expone como comando del agente.

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

La ruta Web ya combina inspección del árbol/Inspector, creación estructural, edición tipada de propiedades y control de la vista previa. La edición arbitraria de scripts no se expone. La aceptación de cada ampliación exige compilación del editor, prueba en Chromium real y verificación de la lectura posterior; no basta con que el patcher compile. La sesión compartida A/B es configurable entre 60 y 3600 segundos (30 minutos por defecto en el host). No se necesita una PC ni un agente local para esta ruta; el puente nativo sigue siendo una herramienta experimental separada.
