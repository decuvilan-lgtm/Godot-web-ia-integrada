# Chromium Godot Controller

## Responsabilidad

Conecta el worker de GitHub Actions con el Godot Web Editor que ya está abierto en su sesión Chromium. La extensión es únicamente un **relay de mensajes**; las operaciones del editor viven en el agente C++ compilado dentro del binario Godot Web.

No crea otro navegador, no instala un addon en el proyecto importado y no sustituye las capturas, el vídeo ni la inspección visual.

## Flujo

    Actions worker
      -> semantic_controller.py
      -> window.postMessage (origen local)
      -> content.js (relay aislado)
      -> page-bridge.js (allowlist)
      -> window.__godotEditorAgent
      -> cola nativa C++ en el hilo del editor
      -> EditorInterface

El adaptador procesa las solicitudes en el hilo principal del editor. Las respuestas se correlacionan por ID y los tiempos de espera se comunican explícitamente.

## Comandos Web disponibles

- editor.list_capabilities
- editor.get_state
- scene.get_tree
- scene.add_node (una primera mutación acotada y deshacible)

El árbol está limitado por profundidad y número de nodos. `scene.add_node` solo acepta clases de nodo allowlisted, nombres identificadores y padres dentro de la escena activa. Usa el historial Undo/Redo del editor y no guarda automáticamente. La extensión y el cliente rechazan comandos fuera de la allowlist. La edición de propiedades, recursos y scripts sigue pendiente.

## Seguridad

- La extensión se limita al origen del editor Godot Web.
- El agente Web no ofrece shell, procesos, acceso general al filesystem ni ejecución arbitraria de JavaScript/GDScript.
- El protocolo de página no debe tratarse como autenticación para secretos: no transporta credenciales y solo expone operaciones explícitas y acotadas.
- Las solicitudes y respuestas están acotadas y correlacionadas.
- La sesión Actions registra el SHA exacto del proyecto y conserva evidencias de esa ejecución.

## Estado

El agente integrado ha respondido a las consultas iniciales en Chromium durante las pruebas del proyecto. La nueva operación `scene.add_node` ya está añadida al patcher y al smoke test; requiere que el editor personalizado actualizado se compile y pase la aceptación en Chromium. El antiguo addon browser-extension/godot-addon no forma parte del flujo activo y fue retirado para evitar dos adaptadores Web que implementaban la misma función de inspección.

La prueba manual con artefacto de compilación se ejecuta mediante .github/workflows/browser-smoke-reuse.yml. Se debe indicar un ID de ejecución de compilación exitosa; no se usa un artefacto histórico por defecto.

## Limitaciones

El control Web ya puede crear nodos de una lista fija; todavía no edita propiedades ni recursos. Tampoco sustituye a Godot Headless para pruebas técnicas ni al editor nativo para operaciones de edición avanzadas. La captura de vídeo del navegador muestra la sesión Chromium, no garantiza capturar una ventana de juego externa del escritorio.
