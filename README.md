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

La meta siguiente es que el sistema pueda manejar el juego durante una ventana configurable (10 segundos por defecto), mediante entradas reales de teclado, ratón y táctil. El controlador debe registrar cada entrada, duración, foco, reacción observable, capturas y errores, y liberar controles incluso cuando la prueba falle.

Los escenarios temporales no se limitan a saltar progresión. Pueden preparar y comprobar cualquier elemento del proyecto, por ejemplo:

- Movimiento, salto, vuelo, navegación y cámara.
- Combate, daño, habilidades, enemigos y estados.
- Interacciones con NPC, objetos, puertas, interruptores y diálogos.
- Inventario, equipamiento, economía, misiones y progreso.
- Menús, HUD, formularios, navegación e interfaz táctil.
- Animaciones, efectos, audio, eventos, transiciones y escenas.
- Casos límite, errores reproducibles y combinaciones de sistemas.

### Ciclo temporal autorizado

Para estos escenarios, el flujo acordado es publicarlos temporalmente en la **rama principal del repositorio del proyecto seleccionado**, para que la revisión pueda importarse en la web. Después de la prueba, se eliminan los archivos temporales y se comprueba que el contenido funcional anterior quede restaurado.

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

**Importante:** el ciclo de escenarios en `main` es el flujo acordado, pero todavía no debe anunciarse como automatizado hasta que estén implementados y probados la publicación, sincronización, controlador y limpieza segura.

Documentación detallada: [Pruebas interactivas y escenarios temporales](docs/INTERACTIVE_GAMEPLAY_TESTING.md).

## Evidencia de la última prueba E2E

Ejecución: [43274843026](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/runs/43274843026).

Resultado verificado:

- Relay: HTTP 200; comprobación de rama y proyecto anidado correcta.
- Proyecto: ZIP precargado, instalado y abierto en Godot Web.
- Editor: interfaz detectada y secuencia completa de 5/5 capturas.
- Juego: F5 abrió el preview; se detectó el menú inicial y se capturaron 8/8 frames.
- Capturas: 1440×900.
- Advertencias: Godot informó errores de carga de `res://scenes/ui/hud.tscn` (`Parse Error: Busy`). No impidieron mostrar el menú, pero el proyecto no puede considerarse libre de errores.
- El probe de responsividad del renderer agotó tiempo; las capturas por Playwright/CDP sí funcionaron.

Esta ejecución **no** envió controles de gameplay ni verificó movimiento, ataques, habilidades o estado interno. Abrir el menú no equivale a probar la jugabilidad.

## Estado de implementación

| Capacidad | Estado |
|---|---|
| Importar repositorios públicos de GitHub | Implementado |
| Seleccionar rama predeterminada o explícita | Verificado |
| Importar proyectos desde subcarpetas | Verificado con fixture y Relay |
| Abrir el proyecto en Godot Web | Verificado en E2E |
| Capturar editor y preview F5 | Verificado en E2E |
| Secuencias y manifiestos de capturas | Verificados en E2E |
| Controlar gameplay con teclado, ratón y táctil | Pendiente |
| Timeline configurable de acciones (10 s por defecto) | Pendiente |
| Descubrir controles y adaptar entradas por proyecto | Pendiente |
| Crear escenarios temporales de cualquier mecánica/interacción | Especificado; implementación pendiente |
| Publicar escenario temporal en `main` y sincronizar commit exacto | Especificado; implementación pendiente |
| Limpieza segura y verificación del estado restaurado | Especificado; implementación pendiente |
| Aserciones funcionales mediante adaptadores de proyecto | Pendiente |
| Actualización incremental de un proyecto ya importado | Pendiente |

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
