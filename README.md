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
- [Flujo Headless + GitHub](docs/HEADLESS_DEVELOPMENT_WORKFLOW.md)
- [Importación GitHub → Godot Web](docs/GITHUB_TO_GODOT_WEB.md)
- [Capacidades de inspección verificadas](docs/VERIFIED_GODOT_INSPECTION_CAPABILITIES.md)
- [Observación visual](docs/VISUAL_OBSERVATION.md)
- [Pruebas interactivas y escenarios temporales](docs/INTERACTIVE_GAMEPLAY_TESTING.md)
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
