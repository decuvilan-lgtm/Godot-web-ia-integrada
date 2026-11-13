# Godot Web IA Integrada

Laboratorio genérico para **inspección visual y pruebas interactivas de proyectos Godot** mediante el Godot Web real desplegado en Render. GitHub conserva el proyecto y su historial; Godot Web solo permite observar y probar una versión sincronizada. El laboratorio nunca es el lugar de almacenamiento, edición definitiva ni entrega del proyecto completo.

Dragon Realm, Escondite, Ajedrez 2c2 y cualquier otro proyecto son objetivos de prueba intercambiables. Ninguno es una dependencia ni recibe un tratamiento especial fuera de perfiles de prueba explícitos.

## 1. Propósito y límites

El sistema permite seleccionar un proyecto Godot, preparar una versión identificable, cargarla en el editor web real de Render, inspeccionar su presentación, ejecutar interacciones y recopilar evidencia técnica.

### Lo que sí hace Godot Web

- Mostrar visualmente el proyecto seleccionado en el editor Godot Web desplegado.
- Ejecutar el proyecto cuando el flujo de importación y el propio proyecto lo permitan.
- Permitir inspecciones del editor, escenas visibles y ejecución del juego.
- Recibir entradas automatizadas de teclado, ratón y táctil.
- Ejecutar secuencias de pruebas durante una sesión activa.
- Producir capturas, grabaciones, observaciones visuales, OCR, eventos, logs y diagnósticos de salida/debugger disponibles.
- Ayudar a comprobar si un cambio produjo el resultado visual o interactivo esperado.

### Lo que no hace Godot Web

- **No entrega el proyecto completo.**
- No es la fuente de verdad de los archivos del juego.
- No conserva ni publica cambios del código del juego como autoridad.
- No sustituye GitHub ni el sistema de trabajo del proyecto.
- No se considera sincronizado solo porque una pestaña siga abierta.
- No garantiza que una modificación en GitHub aparezca automáticamente en una instancia ya importada.
- No debe usarse como repositorio de artefactos de proyecto ni como mecanismo de backup.

Los resultados del laboratorio son evidencia y diagnósticos, no una copia entregable del juego. El proyecto completo se obtiene del repositorio y de la revisión/commit correspondiente.

## 2. Fuentes de verdad y responsabilidades

| Componente | Responsabilidad |
|---|---|
| Repositorio GitHub del juego | Fuente de verdad del código, recursos, ramas, commits e historial del proyecto |
| GitHub Actions | Orquesta la preparación, transferencia/importación, pruebas y publicación de evidencias |
| Relay en Render | Valida y entrega archivos al flujo de importación; ofrece APIs de coordinación y transferencia |
| Godot Web en Render | Laboratorio visual real: editor, ejecución, observación y pruebas interactivas |
| Chromium + Playwright/CDP | Controla la interfaz real del navegador, envía entradas y captura evidencia |
| Godot Headless | Ejecuta validaciones no visuales cuando son compatibles; complementa, no reemplaza, las pruebas visuales |
| Almacenamiento duradero de resultados | Conserva los diagnósticos y evidencias que el flujo publique, según su política de retención |

El repositorio del juego y este repositorio de infraestructura son distintos. Este repositorio contiene el laboratorio y sus workflows; no debe confundirse con el repositorio fuente que se esté probando.

## 3. Principio de sincronización: una versión por prueba

Cada carga del laboratorio representa una revisión concreta del proyecto.

La identidad mínima de una carga es:

- Repositorio del proyecto.
- Rama o referencia solicitada.
- SHA exacto del commit cargado.
- Ruta relativa de la carpeta que contiene `project.godot`.
- Identificador de ejecución/workflow.
- Estado de importación y resultado de las comprobaciones.

### Cuándo se vuelve a importar

**Cada vez que cambie el código o cualquier recurso que deba verificarse, el workflow debe preparar y cargar nuevamente el proyecto actualizado en Godot Web.**

No se confía en hot reload, sincronización automática de carpetas ni detección de cambios de GitHub por parte de una pestaña abierta. El procedimiento es explícito:

1. Identificar el commit nuevo.
2. Descargar y validar el proyecto desde GitHub.
3. Preparar el ZIP de importación para la carpeta Godot seleccionada.
4. Ejecutar el workflow de importación/sincronización.
5. Abrir o importar esa revisión en Godot Web.
6. Confirmar que la versión visible corresponde al SHA esperado.
7. Ejecutar las pruebas visuales e interactivas sobre esa revisión.

Si el código no cambió y la sesión sigue viva con la misma revisión, se pueden enviar más pruebas sin volver a importar. Si el código cambió, primero se sincroniza de nuevo; luego se prueba.

### No confundir sincronización con persistencia de sesión

Una pestaña persistente no significa que sus archivos estén actualizados. La sesión puede seguir abierta mostrando una revisión antigua. El SHA cargado debe verificarse antes de cada conjunto de pruebas.

## 4. Ciclo operativo completo

### 4.1 Solicitud y selección

La solicitud identifica el repositorio, rama/referencia y subcarpeta del proyecto. Se valida que la fuente sea accesible y que la carpeta seleccionada contenga `project.godot`.

### 4.2 Activación bajo demanda

El Relay y los servicios de Render pueden estar suspendidos por inactividad. Solo una solicitud explícita de trabajo debe iniciar el flujo de activación. GitHub Actions puede emitir una petición de salud para despertar el servicio y esperar de forma acotada a que responda.

No se usan cron, heartbeats artificiales ni peticiones periódicas para mantener Render despierto. Se conserva el plan Free y se acepta su suspensión natural.

### 4.3 Preparación de archivos

El workflow descarga el commit elegido, valida rutas y límites, y prepara el paquete temporal de importación. Si el proyecto está en una subcarpeta, el empaquetado coloca `project.godot` en la raíz del ZIP de importación. Las exclusiones necesarias para la ejecución web se registran; nunca modifican el repositorio original.

### 4.4 Importación en el editor real

Playwright abre el Godot Web desplegado en Render y completa el flujo de importación en la interfaz real. No se usa un mock del editor ni una simulación de Godot. Chromium puede ejecutarse en modo headless: eso describe cómo se controla el navegador, no sustituye el servicio Godot Web real.

### 4.5 Inspección y pruebas

Con la revisión cargada se pueden realizar, según el proyecto y las capacidades verificadas:

- Inspección del editor y del árbol de escenas visible.
- Capturas del editor, escenas y juego en ejecución.
- Secuencias de frames y grabaciones de pantalla.
- Entradas de teclado: pulsar, mantener y soltar.
- Entradas de ratón: mover, click, mantener y soltar.
- Entradas táctiles: tocar, mantener, arrastrar y soltar.
- Pruebas de menús, navegación, botones, movimiento, combate y otras interacciones configuradas.
- OCR y comparación de señales visuales.
- Recolección de logs, salida y mensajes del debugger que estén accesibles.
- Registro de acciones enviadas, reacciones observadas y aserciones verificadas por separado.

Una acción enviada no prueba por sí sola que el juego haya reaccionado. Los informes deben distinguir entre entrada ejecutada, respuesta visual observada y condición realmente verificada.

### 4.6 Cambios y nueva sincronización

Si una prueba descubre un defecto y se modifica el código del juego, el cambio se guarda en el repositorio fuente mediante el flujo autorizado. Después se vuelve a ejecutar la importación para cargar el nuevo commit en Godot Web. No se intenta parchear únicamente la copia temporal del editor ni se considera válida una prueba sobre una revisión anterior.

### 4.7 Entrega de resultados

El laboratorio entrega únicamente resultados de prueba y evidencia, por ejemplo:

- Diagnóstico estructurado en JSON.
- Logs de salida y debugger disponibles.
- Errores, advertencias y trazas relevantes.
- Capturas PNG.
- Grabaciones de vídeo/WebM y secuencias de frames.
- OCR y observaciones de pantalla.
- Timeline de acciones y eventos.
- SHA del proyecto probado y manifiesto de la ejecución.
- Informe que indique qué se probó, qué pasó, qué no pudo comprobarse y qué queda pendiente.

**Nunca se empaqueta ni se presenta el proyecto entero como resultado de Godot Web.** Para obtener el juego completo se utiliza su repositorio GitHub y el commit indicado en el informe.

## 5. Sesiones y límites de Render Free

El sistema puede reutilizar una sesión de navegador mientras el proceso y el servicio sigan vivos. Durante esa sesión pueden ejecutarse varias rondas de inspección y pruebas sobre la misma revisión.

- La finalización de una tarea no debe cerrar deliberadamente el navegador.
- La sesión se mantiene solo mientras Render lo permita y haya actividad legítima de trabajo.
- No se envían heartbeats ni tráfico artificial para evitar la suspensión.
- La expiración de la sesión no elimina el proyecto fuente: está en GitHub.
- Si Render suspende o reinicia el servicio, el proceso Chromium y la pestaña en memoria no pueden prometerse como persistentes.
- En la siguiente solicitud explícita, el workflow despierta el servicio y reconstruye el laboratorio cargando nuevamente el proyecto desde el repositorio.
- Los diagnósticos y evidencias ya generados deben publicarse fuera de la memoria efímera del proceso antes de finalizar cada ejecución.

La persistencia es lógica y basada en GitHub/resultados duraderos; no significa que el mismo proceso de navegador sobreviva a una suspensión de Render.

## 6. Contrato de artefactos

Cada ejecución debe publicar un paquete de evidencia separado del proyecto fuente. Como mínimo, cuando estén disponibles:

```text
godot-visual-test-<run-id>/
  result.json
  manifest.json
  logs/
    stdout.log
    stderr.log
    debugger.log
  screenshots/
    editor.png
    game-001.png
  video/
    session.webm
  frames/
    frame-0001.png
  events/
    actions.jsonl
  ocr/
    observations.json
```

La estructura es orientativa: solo se incluyen los archivos que la ejecución haya generado realmente. El manifiesto debe registrar repositorio, rama, SHA, carpeta del proyecto, fecha, workflow, versión del editor si se conoce y estado de cada prueba.

Los artefactos deben ser verificables, tener límites de tamaño y retención documentados y estar separados por ejecución/proyecto. Un resultado parcial debe etiquetarse como parcial; no se inventan capturas, logs ni diagnósticos que no existan.

## 7. Pruebas visuales, interactivas y Headless

Las tres categorías responden preguntas distintas:

| Tipo | Qué comprueba | Qué no demuestra por sí solo |
|---|---|---|
| Visual | Apariencia, disposición, estados visibles, animaciones y respuesta perceptible | Estado interno o lógica no visible |
| Interactiva | Que entradas concretas producen respuestas observables en el juego | Que todos los casos límite o sistemas internos funcionen |
| Headless | Importación, parseo, ejecución automatizada y validaciones compatibles | Que la interfaz se vea bien o que el input real funcione |

Se combinan cuando aportan valor. Los informes nunca convierten una comprobación de una categoría en evidencia de otra.

## 8. Aislamiento y protección de proyectos

- Cada ejecución identifica su proyecto y commit.
- Los perfiles específicos de controles pertenecen a `tests/control-profiles/` y se aplican solo al repositorio objetivo correspondiente.
- El repositorio fuente se modifica únicamente por el flujo autorizado de desarrollo; importar o probar no autoriza escrituras.
- Los proyectos de referencia declarados como solo lectura no se modifican.
- Los archivos temporales de prueba deben estar aislados y tener un manifiesto de limpieza cuando se habilite ese flujo.
- No se sobrescriben archivos del juego desde Godot Web como mecanismo de sincronización.
- No se mezclan resultados ni sesiones de proyectos diferentes.
- No se exponen tokens, claves, códigos de pairing ni URLs firmadas al navegador, a los proyectos o a los logs.
- Repositorios y scripts externos se tratan como código no confiable.
- Se limitan rutas, tamaño de descarga, duración, concurrencia y consumo de recursos.
- No se usan force-push, `reset --hard` ni limpiezas que puedan descartar cambios ajenos.

## 9. Estado de capacidades

La documentación distingue tres estados:

- **Implementado:** existe código para la capacidad.
- **Verificado:** una ejecución identificable produjo evidencia de que funciona.
- **Pendiente:** falta implementación o una prueba concluyente.

No se declara que la sincronización, restauración, importación o una interacción estén terminadas solo porque exista una ruta API o un workflow. La prueba debe confirmar la carga del SHA correcto y la evidencia correspondiente.

## 10. Servicios y enlaces

- Godot Web: https://godot-web-ia-integrada-rt2l.onrender.com/
- Relay: https://godot-web-ia-relay.onrender.com/
- Salud del Relay: https://godot-web-ia-relay.onrender.com/health
- Repositorio del laboratorio: https://github.com/decuvilan-lgtm/Godot-web-ia-integrada
- Workflow de importación: [Godot Web Import](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/workflows/godot-web-import.yml)

## 11. Documentación técnica relacionada

- [Funcionamiento completo del sistema](docs/SYSTEM_OPERATION.md)
- [Arquitectura técnica](docs/ARCHITECTURE.md)
- [Flujo Headless + GitHub](docs/HEADLESS_DEVELOPMENT_WORKFLOW.md)
- [Importación GitHub → Godot Web](docs/GITHUB_TO_GODOT_WEB.md)
- [Capacidades de inspección verificadas](docs/VERIFIED_GODOT_INSPECTION_CAPABILITIES.md)
- [Observación visual](docs/VISUAL_OBSERVATION.md)
- [Pruebas interactivas](docs/INTERACTIVE_GAMEPLAY_TESTING.md)
- [Casos de regresión de importación](docs/GODOT_WEB_IMPORT_REGRESSION_CASES.md)
- [Contrato de comandos visuales](docs/VISUAL_COMMANDS.md)
- [Centro de mando](docs/COMMAND_CENTER.md)
- [Relay y variables de entorno](relay/README.md)

## 12. Recorrido resumido: lo más importante

1. **GitHub es la fuente de verdad:** allí vive y se entrega el proyecto completo.
2. **Godot Web es solo el laboratorio visual:** inspecciona, ejecuta y prueba; nunca entrega el juego entero.
3. **Cada carga queda ligada a un SHA:** siempre sabemos qué versión estamos viendo.
4. **Si cambia el código, se vuelve a importar:** el workflow prepara y carga el proyecto actualizado; no confiamos en actualizaciones automáticas de la pestaña.
5. **Mientras la sesión siga activa, se pueden enviar más pruebas:** no hace falta reimportar si el commit probado no cambió.
6. **Las pruebas generan evidencia:** diagnósticos, logs/debugger, capturas, vídeos, eventos y resultados estructurados.
7. **La sesión no se cierra al terminar una tarea:** Render puede suspenderla naturalmente; no mantenemos el servicio despierto artificialmente.
8. **Si Render suspende, se reconstruye bajo demanda:** se despierta solo cuando hay una nueva solicitud y se vuelve a cargar el commit requerido.
9. **La evidencia se conserva fuera de la memoria efímera:** una suspensión no debe borrar resultados ya publicados.
10. **Nunca confundimos evidencia con proyecto:** el informe indica dónde está el código fuente y qué SHA fue probado.
