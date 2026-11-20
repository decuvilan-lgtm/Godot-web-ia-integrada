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

El adaptador procesa las solicitudes en el hilo principal del editor. Las respuestas se correlacionan por ID y los tiempos de espera se comunican explícitamente. La sesión compartida A/B usa un único Chromium: A mantiene el navegador y B envía comandos secuenciados. La duración predeterminada es 30 minutos; el host request admite `duration_seconds` entre 60 y 3600 y B puede cerrar la sesión con `stop`.

## Comandos Web disponibles

- editor.list_capabilities
- editor.get_state
- editor.get_selection (lectura de selección actual)
- scene.select_node (selección explícita por ruta relativa y consulta del nodo seleccionado)
- scene.get_tree (jerarquía limitada, con rutas relativas a la raíz de la escena)
- scene.inspect_node (lectura acotada de propiedades visibles en el Inspector para un nodo)
- scene.add_node (creación de nodos allowlisted, deshacible y sin guardado automático)
- scene.set_property (edición de propiedades expuestas por el Inspector, con Undo/Redo)
- project.list_files (inventario recursivo acotado del proyecto)
- project.read_file (lectura UTF-8 de scripts, escenas y configuración)
- project.write_file (escritura UTF-8 verificada de scripts, escenas y configuración; máximo 10 KB por operación)
- resource.inspect (carga y consulta del tipo de un recurso)
- scene.save (guardado explícito de la escena activa con comprobación del resultado de Godot)
- Workflow B puede agrupar hasta 12 llamadas `scene.add_node` en una construcción secuencial y verificar que todos los nodos aparecen en el árbol.

El Inspector devuelve hasta 80 propiedades marcadas por Godot para el editor, con nombre, tipo y valor serializado. La edición de propiedades utiliza el historial Undo/Redo. Los scripts se editan como archivos de texto UTF-8 mediante `project.write_file`; los cambios se leen de vuelta para verificar el contenido.

El árbol está limitado por profundidad y número de nodos. `scene.add_node` solo acepta clases de nodo allowlisted, nombres identificadores y padres dentro de la escena activa. Usa el historial Undo/Redo del editor y no guarda automáticamente. La extensión y el cliente rechazan comandos fuera de la allowlist. La edición de propiedades, recursos y scripts sigue pendiente.

## Selección y jerarquía
`scene.get_tree` devuelve la jerarquía recursiva acotada. `scene.select_node` selecciona un nodo por ruta relativa dentro de la escena activa y `editor.get_selection` permite consultar la selección real del editor. Las rutas absolutas y los segmentos de traversal se rechazan.

## Output y Debugger
Las capturas de Chromium conservan el contexto visual de los paneles abiertos. La lectura textual de Output y Debugger requiere extraer el contenido de los controles visibles del editor; no se deben inventar mensajes a partir de una captura. La extracción focalizada de ambos paneles queda como siguiente extensión del controlador.

## Output y Debugger: captura + texto
El comando de transporte `capture_editor_panel` acepta `panel: "Output"` o `panel: "Debugger"`. B pulsa la pestaña correspondiente en la sesión Chromium, recoge texto visible de la interfaz (máximo 15.000 caracteres) y guarda una captura PNG de la ventana del editor. El texto se marca como truncado si excede el límite. Esto permite correlacionar el contenido legible con el estado visual, sin afirmar que el panel contiene mensajes que no estén visibles.

## Vista previa del juego en ejecución

Workflow B dispone de una ruta de preview separada de la edición de escena:

- `run_game`: enfoca el editor y envía F6 para ejecutar la escena actual.
- `game_view`: abre la pestaña Game y detecta el canvas visible del runtime, también dentro de iframes.
- `game_click`: envía un click con coordenadas normalizadas al canvas de juego detectado.
- `game_input`: mantiene una tecla allowlisted durante un intervalo acotado y siempre la libera al terminar.

La prueba real en Chromium ejecutó F6, detectó un canvas de preview de 1280×720, envió un click y una entrada de teclado y volvió a comprobar la misma URL y el canvas visible. Esto confirma entrega de entradas al viewport, no una reacción de gameplay concreta. Para afirmar que una mecánica respondió, el proyecto debe aportar controles conocidos y una aserción visual o funcional independiente.

Las capturas PNG completas quedan en el artefacto de evidencia de Workflow A. B también puede solicitar una vista JPEG inline de la página o del canvas de juego (hasta 42 KB antes de Base64), que vuelve por el canal de comandos mientras A sigue abierta; así el razonador puede inspeccionar visualmente el resultado sin cerrar Chromium.

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

El control Web ya puede crear nodos de una lista fija; todavía no edita propiedades ni recursos. Tampoco sustituye a Godot Headless para pruebas técnicas. La escritura actual cubre archivos de texto del proyecto, no importación binaria de imágenes/audio/modelos ni transferencias grandes por fragmentos. Esas operaciones requieren el canal de artefactos y un ciclo de importación/validación adicional. El agente tampoco sustituye a Godot Headless para pruebas técnicas; el puente nativo es opcional y separado. La captura de vídeo del navegador muestra la sesión Chromium, no garantiza capturar una ventana de juego externa del escritorio.
