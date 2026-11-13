# Godot Web IA Integrada

Entorno genérico para importar, inspeccionar, modificar y probar proyectos Godot desde el navegador, con automatización y evidencia reproducible. No está acoplado a un juego, género, repositorio, nombre de proyecto ni conjunto fijo de controles.

Dragon Realm y Escondite son proyectos de referencia intercambiables para validar el sistema. No son dependencias ni valores especiales.

## Objetivos

- Importar repositorios públicos de GitHub indicando rama y subcarpeta.
- Abrir proyectos Godot en Godot Web y observar editor y ejecución.
- Automatizar entradas reales de teclado, ratón y táctil.
- Preparar escenarios temporales dentro del proyecto real para probar mecánicas e interacciones.
- Capturar secuencias, registrar eventos y producir resultados verificables.
- Mantener separados los proyectos, revisiones y artefactos de cada ejecución.
- Diferenciar claramente capacidades implementadas, probadas y pendientes.

## Arquitectura

| Componente | Responsabilidad |
|---|---|
| GitHub | Código fuente, ramas, revisiones e historial de los proyectos |
| Relay | Descarga controlada de repositorios públicos y entrega de ZIP al navegador |
| Godot Web | Project Manager, editor y ejecución visual del proyecto |
| Godot Headless | Importación, validación y pruebas sin interfaz cuando sea compatible |
| Playwright / Chromium | Automatización del navegador, entradas y capturas |
| GitHub Actions | Orquestación de importación, comprobaciones y artefactos |
| Render | Alojamiento del editor web y del Relay |

Una prueba Headless no sustituye una prueba visual. Una captura tampoco demuestra por sí sola que una mecánica interna funcione.

## Abrir un proyecto

Editor publicado: https://godot-web-ia-integrada-rt2l.onrender.com/

Se puede preparar una importación mediante URL:

```text
https://godot-web-ia-integrada-rt2l.onrender.com/?repo=OWNER/REPOSITORY
https://godot-web-ia-integrada-rt2l.onrender.com/?repo=OWNER/REPOSITORY&branch=main&path=carpeta/proyecto
```

- `repo`: repositorio público de GitHub.
- `branch`: rama seleccionada; si se omite, se resuelve la rama predeterminada.
- `path`: carpeta relativa que contiene `project.godot`; si se omite, se usa la raíz.

El Relay valida las rutas, comprueba `project.godot` y reempaqueta proyectos de subcarpetas para que el archivo del proyecto quede en la raíz del ZIP. La importación inicial no implica que una pestaña ya abierta se actualice automáticamente: para probar una revisión nueva debe sincronizarse/importarse esa revisión y comprobar su identidad.

## Workflow E2E

[**Importar repositorio en Godot Web — GitHub Actions**](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/workflows/godot-web-import.yml)

El workflow actual:

1. Valida el repositorio público y resuelve rama, subcarpeta y nombre del proyecto.
2. Abre Godot Web en Chromium.
3. Comprueba aislamiento del navegador y la entrega del ZIP por el Relay.
4. Instala y abre el proyecto seleccionado.
5. Confirma la apertura mediante logs y detección visual/OCR.
6. Captura el editor y una secuencia de frames.
7. Envía F5 para intentar abrir el preview del juego y captura otra secuencia si se detecta.
8. Publica `result.json`, eventos, OCR, capturas y manifiestos como artefactos de Actions.

Parámetros de ejecución manual: `repository_url`, `branch`, `project_path`, `startup_timeout`, `editor_frames`, `editor_interval_ms`, `game_frames` y `game_interval_ms`.

Los artefactos se conservan durante 14 días. Las secuencias se validan por cantidad de frames, dimensiones y existencia de PNG; una secuencia incompleta no debe presentarse como completa.

## Sesiones persistentes: importación, perfiles y evidencias

Esta ruta es distinta del workflow E2E de importación inicial. Mantiene una pestaña real de Chromium abierta en el Relay y permite continuar inspeccionando el mismo proyecto entre tareas mientras el proceso de Render permanezca activo.

### Identidad obligatoria de cada ejecución

Toda ejecución debe registrar y comprobar conjuntamente:

- Repositorio GitHub en formato `OWNER/REPOSITORY`.
- Rama solicitada.
- Ruta relativa que contiene `project.godot` (vacía si está en la raíz).
- SHA completo e inmutable del commit que se quiere importar.
- ID de sesión persistente, ID de ejecución de GitHub Actions e intento del workflow.
- Estado del conector Godot, número de canvas y evidencia generada.
- Estado del perfil del juego y SHA exacto contra el que fue verificado.
- ID, clave de objeto, tamaño y SHA-256 del paquete persistido.

La rama identifica de dónde se resuelve el proyecto; el SHA identifica qué contenido exacto se probó. No se considera correcta una importación solo porque la página haya cargado o muestre canvas: el conector debe informar `phase: started` y el `commitSha` debe coincidir exactamente con el SHA solicitado.

### Workflow de sesión persistente

[**Godot Web persistent session smoke test**](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/workflows/persistent-session-smoke.yml)

Se puede iniciar manualmente con estos parámetros:

| Entrada | Obligatoria | Uso |
|---|---:|---|
| `repository` | Sí | Repositorio público `OWNER/REPOSITORY` |
| `branch` | No | Rama; por defecto `main` |
| `commit_sha` | No | SHA completo. Si se omite, se resuelve el HEAD de la rama al comenzar |
| `project_path` | No | Carpeta de `project.godot`; por defecto la configurada en el workflow |
| `profile_command` | No | Slug de un comando declarado por el propio juego; por defecto `smoke-test` |
| `reimport_existing` | No | Reutilizar el mismo contexto de navegador para importar otra revisión del mismo repositorio |
| `wait_seconds` | No | Espera inicial breve antes de consultar el estado real; entre 5 y 120 segundos |
| `import_timeout_seconds` | No | Límite de espera de importación; entre 60 y 600 segundos, por defecto 480 |

El proceso correcto es:

1. Esperar a que el Relay publique la ruta de sesión persistente y que el editor esperado esté desplegado.
2. Resolver y fijar el SHA completo; abrir o reutilizar la sesión asociada al proyecto.
3. Esperar la demora inicial configurada y luego consultar periódicamente el estado real del conector, no asumir que una pausa fija equivale a importación terminada.
4. En cada consulta, renovar el heartbeat de la tarea y registrar fase, SHA importado y cantidad de canvas.
5. Continuar solo cuando el conector indique `started`, el SHA importado coincida exactamente y exista al menos un canvas.
6. Leer el manifiesto de laboratorio desde el mismo SHA. Ejecutar un comando del juego solo si el perfil y ese comando están verificados contra ese SHA.
7. Inspeccionar la interfaz, tomar una captura, completar la tarea y pedir al Relay que persista el ZIP privado.
8. Descargar el ZIP desde el Relay, validar su estructura con `unzip -t` y conservar el índice de la ejecución como artefacto de Actions.
9. No cerrar la pestaña al terminar. Render puede suspenderla naturalmente tras su TTL de inactividad; no usar tráfico artificial para mantenerla despierta.

Si se alcanza el límite sin importar el proyecto, la ejecución debe fallar con el último estado observado. No debe crear un paquete de tarea que parezca una prueba completa. Una fase `downloading` significa que la importación sigue en curso; no es equivalente a `started`.

### Manifiesto de laboratorio propiedad de cada juego

Cada repositorio de juego puede incluir esta estructura, en la raíz del repositorio:

```text
godot-lab/
├── lab-manifest.json
├── control-profile.json
└── commands/
    └── smoke-test.json
```

El Relay siempre lee esos archivos desde el SHA exacto importado. No mantiene un catálogo global de controles, no copia perfiles de otro juego y no modifica el repositorio de origen.

Ejemplo de `godot-lab/lab-manifest.json`:

```json
{
  "schema_version": 1,
  "project": {
    "name": "Nombre del juego",
    "project_path": "carpeta/del/proyecto"
  },
  "control_profile": "control-profile.json",
  "commands": [
    {
      "name": "smoke-test",
      "file": "commands/smoke-test.json",
      "description": "Comprueba que el proyecto abre y responde",
      "verification": {
        "status": "pending",
        "commit_sha": null
      }
    }
  ]
}
```

Ejemplo de `godot-lab/control-profile.json`:

```json
{
  "schema_version": 1,
  "verification": {
    "status": "pending",
    "commit_sha": null
  },
  "controls": {
    "move_right": {
      "type": "key",
      "key": "D"
    },
    "jump": {
      "type": "key",
      "key": "Space"
    },
    "start_button": {
      "type": "text",
      "text": "Jugar"
    },
    "primary_action": {
      "type": "point",
      "x": 0.82,
      "y": 0.88
    }
  }
}
```

Ejemplo de `godot-lab/commands/smoke-test.json`:

```json
{
  "schema_version": 1,
  "name": "smoke-test",
  "verification": {
    "status": "pending",
    "commit_sha": null
  },
  "steps": [
    { "op": "inspect" },
    { "op": "assert_canvas" },
    { "op": "screenshot" },
    { "op": "wait", "ms": 1000 },
    { "op": "tap_control", "control": "start_button" },
    { "op": "wait", "ms": 1000 },
    { "op": "inspect" },
    { "op": "screenshot" }
  ]
}
```

Estos ejemplos son plantillas: los nombres, textos, teclas, coordenadas y pasos deben descubrirse en el juego real. Un manifiesto nuevo empieza como `pending`; no debe marcarse como verificado por el mero hecho de que el JSON pase la validación.

### Cómo se verifica un perfil

Estados permitidos:

- `pending`: descubierto o editado, pero todavía no reproducido y confirmado en el editor.
- `verified`: reproducido correctamente y asociado a un SHA completo exacto.
- `obsolete`: su SHA ya no coincide con la revisión que se está importando o el comportamiento cambió.

La verificación se realiza en el navegador real: inspeccionar la pantalla, probar cada control, observar el efecto, repetir para comprobar consistencia y registrar evidencia. Si se modifica un control o un comando, se devuelve a `pending`. Una nueva revisión no hereda automáticamente la verificación de la anterior.

Tipos de control permitidos:

- `key`: una tecla incluida en la lista segura del Relay.
- `text`: texto visible que se localiza de forma exacta.
- `point`: coordenadas normalizadas entre 0 y 1 relativas al viewport. Son un fallback frágil y deben acompañarse de una comprobación visual.

Operaciones permitidas en comandos declarativos:

- `inspect`, `screenshot`, `assert_canvas`, `wait`.
- `tap_control` y `hold_control` sobre controles declarados.
- `click_text`, `press_key` y `assert_text`.

Límites actuales del validador: hasta 20 comandos por manifiesto, 40 pasos por comando, 100 controles por perfil, 5 segundos por espera individual, 20 segundos acumulados de esperas/retenciones, 2 segundos por retención de tecla y 120 segundos de ejecución por comando. El Relay rechaza rutas absolutas, traversal, tipos de control desconocidos, teclas fuera de la lista permitida y operaciones no declaradas. No ejecuta shell, Python, JavaScript ni scripts arbitrarios que vengan del juego.

Si el repositorio no contiene `godot-lab/lab-manifest.json`, la respuesta correcta es `profile_status: not_found`: el laboratorio todavía puede inspeccionar y capturar la interfaz, pero no inventa comandos ni importa instrucciones de otro repositorio.

### Persistencia privada de evidencias

El Relay utiliza el bucket privado Neon Object Storage `godot-visual-captures`. Las credenciales existen únicamente como variables de entorno del servicio Render; no deben copiarse a GitHub, README, repositorios de juegos, navegador, archivos de evidencia ni logs.

Variables requeridas en Render:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_ENDPOINT_URL_S3`
- `AWS_REGION`

La credencial debe tener solo los permisos de almacenamiento que necesite el Relay. El endpoint y la región deben corresponder al branch de Neon que contiene el bucket.

El endpoint `POST /v1/persistent-sessions/{id}/tasks/complete` crea un ZIP con `task-result.json`, eventos y capturas. El Relay lo sube al bucket privado, registra SHA-256 en los metadatos y devuelve un `artifact_id`, `object_key`, tamaño y URL de recuperación. El workflow descarga ese paquete por el Relay y valida el ZIP antes de declarar la tarea completa. La sesión de Chromium permanece abierta.

La prueba integral solo se considera aprobada cuando se demuestran todos estos puntos: importación del SHA exacto, inspección y captura reales, respuesta de finalización, objeto visible en Neon, recuperación del ZIP y coincidencia de SHA-256. Que Render esté `live`, que exista una captura en memoria o que Actions haya subido un índice JSON no demuestra por sí solo que Neon haya guardado el paquete.

### Diagnóstico rápido de fallos

| Síntoma | Interpretación / siguiente comprobación |
|---|---|
| Relay no expone `/v1/persistent-sessions` | Revisar despliegue, OpenAPI y logs del Relay |
| Editor no informa la versión esperada | Revisar despliegue del editor web |
| Conector permanece en `downloading` | La descarga/importación no terminó; revisar red, tamaño del ZIP, ruta del proyecto y logs del navegador |
| `started` con SHA distinto | No aceptar el proyecto; comprobar ref fijada y sincronización |
| `profile_status: not_found` | Falta el manifiesto en el SHA del repositorio; no es un error del editor |
| `VISUAL_STORAGE_NOT_CONFIGURED` | Falta una de las cuatro variables S3 en Render |
| Error al subir a Neon | Revisar endpoint, región, permisos de la credencial, bucket y logs del Relay |
| Tarea completada pero ZIP no se recupera | Revisar clave del objeto, permisos de lectura y verificación de integridad |

El intento `43503528165` confirmó que el editor podía abrir, pero también expuso el límite de memoria del Relay: Render terminó la instancia con `OOMKilled` al alcanzar el límite de **512 MiB**, durante la descarga/importación del proyecto. El conector seguía en `downloading`; la tarea no llegó a completarse y no creó un objeto en Neon. El workflow ahora espera el estado real de importación y registra el último estado observado. Además, la sesión persistente usa un viewport inicial de **1024×640** para reducir el coste de las superficies de renderizado sin desactivar la interacción. Esta reducción es una mitigación que debe medirse, no una garantía: si vuelve a ocurrir OOM, el navegador persistente deberá trasladarse a un runtime con más memoria; no se debe ampliar el plan ni generar costes sin autorización. Hasta verificar importación, captura, subida, recuperación e integridad del ZIP, la persistencia integral permanece **pendiente**.

## Pruebas interactivas y escenarios temporales

El controlador ya supera una prueba de gameplay real en Godot Web. La sesión de regresión de Dragon Realm usa un perfil versionado y combina teclado, ratón y gestos táctiles continuos. El controlador genérico no depende de ese juego: los controles específicos viven en perfiles de prueba separados.

### Evidencia de control real

Ejecución verificada: [GitHub Actions #43330622553](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/runs/43330622553).

- 11 de 11 acciones enviadas en una misma sesión.
- Teclado: movimiento, salto y ataque mantenido.
- Ratón: inicio de partida y ejecución del botón de combate.
- Ataque: OCR detectó el mensaje visible `PUÑO BÁSICO · 29 daño`.
- Joystick táctil: el arrastre cambió la coordenada X del minimapa de `0266` a `0017`; al soltar, la palanca regresó al centro.
- Grabación continua: un WebM de la sesión completa, 1440×900.
- Relay: validación de repositorio, rama y ZIP aprobada.

El controlador admite teclado `press/down/up`, ratón `move/click/down/up` y táctil `tap/down/move/up`. Los gestos táctiles continuos se envían mediante eventos CDP y se liberan automáticamente si una acción falla. Los perfiles de control se guardan en `tests/control-profiles/`; el workflow carga el perfil de Escondite desde un archivo versionado, en vez de duplicar las acciones en YAML.

### Advertencias que siguen abiertas

- Godot registró `Parse Error: Busy` y `Failed loading resource` para `res://scenes/ui/hud.tscn`. El HUD sí apareció y respondió durante la prueba, pero el proyecto conserva esa advertencia. El repositorio de referencia se mantiene de solo lectura.
- El probe de responsividad del renderer agotó su tiempo. Las capturas, la entrada de controles y la grabación sí funcionaron mediante Playwright/CDP.
- Una entrada enviada no se considera prueba de funcionamiento por sí sola: el informe separa acciones enviadas, reacción visual y aserciones OCR.

### Siguiente etapa

La prioridad es generalizar los perfiles y las comprobaciones semánticas para otros proyectos, añadir emulación de viewport móvil y reforzar la detección de escenas/controles sin depender de Escondite. Los escenarios temporales dentro del proyecto real siguen pospuestos hasta que el flujo genérico de control y verificación esté suficientemente validado.

### Ciclo temporal autorizado (fase posterior)

Este ciclo no se implementará todavía. Primero debe quedar demostrado el control interactivo del juego en ejecución. Una vez superado ese requisito, el flujo acordado será publicar temporalmente en la **rama principal del repositorio del proyecto seleccionado**, para que la revisión pueda importarse en la web. Después de la prueba, se eliminan los archivos temporales y se comprueba que el contenido funcional anterior quede restaurado.

1. Registrar repositorio, SHA base, rama y estado inicial.
2. Crear un manifiesto único con los archivos nuevos y los archivos existentes que se modificarán.
3. Preparar el escenario dentro del proyecto Godot real, reutilizando sus recursos, autoloads y sistemas.
4. Publicar los cambios temporales en `main` mediante commits normales e identificables.
5. Importar en Godot Web el commit exacto y comprobar que corresponde al escenario preparado.
6. Ejecutar las acciones y reunir evidencia visual y funcional.
7. Eliminar solo los archivos creados por la prueba y restaurar exactamente cualquier archivo preexistente modificado.
8. Verificar que no se hayan eliminado cambios ajenos y que el repositorio vuelva al contenido funcional previo.

La limpieza no debe usar force-push, `reset --hard` ni operaciones que reescriban el historial o descarten commits de terceros. Si aparecen cambios ajenos o el HEAD no coincide con lo esperado, la limpieza automática debe detenerse y preservar el estado para revisión. Las pruebas deben serializarse para evitar que dos escenarios temporales se pisen.

El editor web alojado en Render no necesita reconstruirse por cada cambio del proyecto externo: el escenario se refleja al importar/sincronizar la revisión nueva del repositorio objetivo. El auto-deploy de Render corresponde al repositorio del propio editor.

**Estado del controlador:** la primera versión admite pulsaciones/soltados de teclado, movimiento/click/presión de ratón y toque táctil puntual. Incluye timeline con duración configurable (10 segundos por defecto), capturas periódicas y liberación de teclas/botones si ocurre un error. Las pruebas unitarias pasaron en [Actions 43278159189](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/runs/43278159189); la integración E2E del navegador está en [ejecución 43278226182](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/runs/43278226182). Los gestos táctiles continuos y el flujo completo de escenarios temporales aún no están terminados.

**Prioridad actual:** lograr control real y verificable del juego en ejecución. No iniciar todavía la creación ni publicación de escenarios temporales. El ciclo en `main` queda documentado para la fase posterior, pero no está automatizado.

Documentación detallada: [Pruebas interactivas y escenarios temporales](docs/INTERACTIVE_GAMEPLAY_TESTING.md).

## Evidencia de la última prueba E2E

Ejecución: [43330622553](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/runs/43330622553).

- Relay: aprobado.
- Proyecto Dragon Realm: importado y abierto en Godot Web.
- Gameplay: 11/11 acciones enviadas.
- Ataque: mensaje de 29 de daño detectado por OCR.
- Joystick táctil: coordenada X del minimapa cambió de 0266 a 0017.
- Grabación: un WebM continuo de la sesión, conservado como artefacto.
- Advertencias: `hud.tscn` informó `Parse Error: Busy`; el probe de responsividad agotó tiempo aunque la captura y los controles sí funcionaron.

El proyecto de referencia Escondite no se modificó.

## Seguridad y protección de proyectos

- No exponer tokens, claves ni credenciales al navegador, al proyecto importado o a los logs.
- Tratar repositorios y scripts externos como código no confiable.
- Limitar rutas, tamaños, duración y consumo de recursos.
- Mantener separados los proyectos y sus artefactos.
- Registrar SHA base, commits temporales y manifiesto de archivos.
- No sobrescribir archivos originales sin guardar su contenido y plan de restauración.
- No borrar ni revertir cambios ajenos.
- Separar observación visual de telemetría funcional; no inferir estado interno solo por píxeles.
- No declarar una capacidad terminada sin pruebas y artefactos que la demuestren.

## Servicios

- Editor: https://godot-web-ia-integrada-rt2l.onrender.com/
- Relay: https://godot-web-ia-relay.onrender.com/
- Salud del Relay: https://godot-web-ia-relay.onrender.com/health
- Repositorio: https://github.com/decuvilan-lgtm/Godot-web-ia-integrada

## Documentación

- [Arquitectura técnica](docs/ARCHITECTURE.md)
- [Plantilla detallada de README para cada repositorio de juego](docs/GAME_REPOSITORY_README_TEMPLATE.md)
- [Flujo Headless + GitHub](docs/HEADLESS_DEVELOPMENT_WORKFLOW.md)
- [Importación GitHub → Godot Web](docs/GITHUB_TO_GODOT_WEB.md)
- [Capacidades de inspección verificadas](docs/VERIFIED_GODOT_INSPECTION_CAPABILITIES.md)
- [Observación visual](docs/VISUAL_OBSERVATION.md)
- [Pruebas interactivas y escenarios temporales](docs/INTERACTIVE_GAMEPLAY_TESTING.md)
- [Casos de regresión de importación Godot Web](docs/GODOT_WEB_IMPORT_REGRESSION_CASES.md)
- [Contrato de comandos visuales](docs/VISUAL_COMMANDS.md)
- [Centro de mando](docs/COMMAND_CENTER.md)
- [Relay y variables de entorno](relay/README.md)

## Principios para continuar

1. El sistema es genérico: no hay un juego de referencia obligatorio.
2. Cada ejecución identifica repositorio, rama, subcarpeta y commit.
3. Los controles, escenas y recursos se descubren o configuran por proyecto.
4. Las pruebas Headless, visuales e interactivas se complementan.
5. Cada prueba produce evidencia trazable y estados honestos.
6. Los escenarios temporales pueden probar cualquier sistema o interacción.
7. La publicación temporal en `main` debe ser reversible, auditada y seguida de limpieza verificada.
8. Las capacidades pendientes no se presentan como terminadas.
