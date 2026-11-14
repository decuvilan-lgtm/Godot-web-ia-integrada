# Godot Web IA Integrada

Laboratorio genérico para que ChatGPT produzca y pruebe proyectos Godot. **La producción ocurre en el entorno Linux de ChatGPT con Godot Headless; Godot Web en Chromium se utiliza después para ejecutar, inspeccionar y obtener evidencia visual del proyecto.**

El laboratorio no contiene instrucciones particulares de cada juego ni es el lugar donde se desarrolla su contenido. Cada proyecto conserva su identidad, sus instrucciones y sus pruebas en su propio repositorio.

## Flujo oficial de trabajo

```text
Repositorio del juego (GitHub)
          |
          | recuperar proyecto y SHA
          v
Entorno Linux de ChatGPT
  - Godot Headless
  - experimentar y modificar libremente
  - importar, ejecutar y probar técnicamente
          |
          | solo cambios definitivos
          v
Repositorio del juego (GitHub / main)
          |
          | sincronizar el SHA más reciente
          v
GitHub Actions
  - reutilizar la sesión Chromium activa, si existe
  - o iniciar una sesión nueva
  - cargar/importar la revisión exacta del proyecto
  - ejecutar el juego y operar su interfaz
          |
          v
Evidencias: vídeo + capturas + Output + Debugger disponible
          |
          v
Artifact de Actions y/o Neon
          |
          v
ChatGPT inspecciona resultados, detecta fallos y vuelve a Linux
```

### 1. Producción: ChatGPT + Linux + Godot Headless

ChatGPT utiliza el entorno Linux de trabajo disponible en su sesión. Godot Headless es el motor de producción y validación técnica; no lo ejecuta el laboratorio, Render ni el navegador.

- Recuperar el repositorio elegido mediante la integración de GitHub y registrar el commit SHA de origen.
- Trabajar sobre una copia local persistente mientras esté disponible el entorno.
- Experimentar, crear, modificar y descartar cambios libremente en esa copia.
- Ejecutar importación, comprobaciones, escenas, scripts y pruebas compatibles con Headless.
- Revisar los cambios y distinguir experimentos de trabajo definitivo.
- Publicar en el repositorio del juego únicamente los cambios que ya se hayan considerado definitivos y revisado.
- No reemplazar el repositorio completo por una copia local ni sobrescribir cambios remotos ajenos.

**Ubicación exacta del runtime Linux Headless:** está en el repositorio [Godot 4.7.2 modificado](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado), rama `feature/linux-headless-agent-runtime` (no en `main`). El workflow que lo construye es [`.github/workflows/build-godot-linux-headless.yml`](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/blob/feature/linux-headless-agent-runtime/.github/workflows/build-godot-linux-headless.yml); la guía está en [`docs/LINUX_HEADLESS_AGENT.md`](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/blob/feature/linux-headless-agent-runtime/docs/LINUX_HEADLESS_AGENT.md). La rama se comprobó comparándola con `main`: contiene 13 commits adicionales e incorpora el workflow Linux. El ejecutable esperado es `godot-source/bin/godot.linuxbsd.editor.x86_64`, empaquetado como `godot-linux-headless-agent.tar.gz`. La existencia del workflow y su receta está confirmada; antes de usarlo hay que comprobar que una ejecución haya terminado correctamente y que el artefacto o Release exista y sea descargable.

**Disponibilidad de Godot Headless:** primero comprobar si el ejecutable compatible sigue disponible en el entorno Linux. Si no está disponible, recuperarlo mediante el repositorio de Godot modificado indicado para este flujo: [Godot 4.7.2 modificado](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado). Revisar sus workflows y artefactos para obtener una distribución Linux Headless compatible. No confundir el APK del editor Android con el ejecutable Linux Headless; el APK no sirve para este trabajo. Si el repositorio no ofrece una distribución Linux utilizable, informar esa limitación y no afirmar que Headless está disponible.

El entorno Linux de ChatGPT puede trabajar sin salida directa a Internet ni resolución DNS. Para mover el proyecto entre el entorno de trabajo y el puesto de revisión se utilizará el sistema de transferencia ya existente del usuario, que no depende de Internet ni de DNS. No sustituirlo por un relay, proxy ni por los clientes auxiliares de sincronización de la rama Linux.

**Herramientas auxiliares conservadas, pero fuera del flujo activo:** la rama `feature/linux-headless-agent-runtime` también incluye `tools/godot_project_sync.py` y `tools/godot_project_publish.py`, junto con sus pruebas. Son clientes del relay remoto y requieren `GODOT_AGENT_TOKEN`; no se usarán para nuestro flujo porque ya existe un mecanismo de transferencia que no necesita Internet ni DNS. No eliminarlos ni modificarlos por esta decisión: quedan preservados en su repositorio como herramientas independientes, sin ser una dependencia del laboratorio.

### 2. Publicación: repositorio del proyecto elegido

GitHub es la fuente oficial de los cambios definitivos.

- Cada tarea comienza identificando repositorio, rama y SHA base.
- Los experimentos permanecen en la copia local de Linux.
- Antes de publicar, revisar el conjunto real de archivos creados, modificados y eliminados.
- Publicar solo los archivos necesarios, mediante la integración GitHub de ChatGPT.
- La rama de trabajo acordada es `main`, salvo que el proyecto indique otra cosa.
- Si `main` avanzó desde el SHA base, detener la publicación y reconciliar los cambios; no sobrescribir trabajo ajeno.
- Registrar el commit definitivo para que la revisión visual cargue exactamente esa versión.

No se publica cada experimento. Se publica cuando el cambio es definitivo.

### 3. Revisión visual: GitHub Actions + Chromium + Godot Web

Después de publicar un cambio definitivo, ChatGPT ordena a GitHub Actions que compruebe el proyecto actualizado.

1. Resolver el repositorio, rama, ruta del proyecto y SHA más reciente.
2. Comprobar si existe una sesión Chromium activa que pueda reutilizarse.
3. Si existe, sincronizar/importar en ella la revisión nueva del proyecto seleccionado.
4. Si no existe o ya no es válida, iniciar una sesión nueva mediante Actions y cargar el proyecto más reciente en Godot Web dentro de Chromium.
5. Confirmar que el editor abrió el SHA exacto solicitado.
6. Ejecutar el juego y utilizar entradas reales para recorrer sus pantallas y probar sus interacciones.
7. Capturar la interfaz completa y el comportamiento durante la ejecución.
8. Recuperar los artefactos y analizar los resultados.

La sesión activa no debe confundirse con el proyecto: una sesión puede reutilizarse, pero siempre debe comprobarse qué repositorio y SHA están cargados. Nunca asumir que una pestaña abierta ya contiene el último commit.

**Godot Web es el puesto visual de ChatGPT**, alojado en Render y controlado durante las pruebas mediante Chromium/Playwright en Actions. No es el entorno principal de producción ni sustituye a Headless. El editor Godot Android es el puesto del usuario y permanece separado.

### 4. Evidencias que debe obtener Actions

La revisión visual debe permitir observar el juego, no limitarse a comprobar que el editor cargó.

Recopilar, según lo que la build de Godot Web y el navegador permitan obtener:

- Vídeo de la sesión de juego, con la interfaz y las interacciones.
- Capturas de pantalla del editor, escenas, menús, HUD y gameplay.
- Secuencias de frames con orden y marcas temporales.
- **Output:** mensajes, advertencias, errores y trazas disponibles de la ejecución.
- **Debugger:** errores y datos de depuración que realmente exponga la build web.
- Logs de Chromium, consola y automatización cuando ayuden a diagnosticar.
- Metadatos: repositorio, rama, SHA cargado, ruta del proyecto, escena si se conoce, ID del workflow, ID de sesión, duración y estado de la prueba.

La build Godot Web puede no exponer todas las funciones del Debugger del editor de escritorio. Obtener toda la información disponible, indicar qué campos no existen o no se pudieron extraer y no inventar datos. La salida Headless y la salida de la ejecución visual son evidencias distintas; conservar ambas.

Las evidencias deben pertenecer a una sola ejecución y señalar el SHA probado. Un vídeo o una captura demuestra lo que se ve, no necesariamente que la lógica interna sea correcta. Las acciones enviadas tampoco prueban por sí solas que el juego haya reaccionado: registrar por separado acciones enviadas, reacción observada y aserciones verificadas.

### 5. Recuperación de resultados: Actions y Neon

ChatGPT debe poder obtener los resultados de cualquiera de estas vías, según estén disponibles:

- **Artifact de GitHub Actions:** descargar el paquete generado por el workflow y analizar sus vídeos, capturas, logs, manifiestos y resultados.
- **Neon:** recuperar directamente las evidencias y metadatos persistidos cuando el flujo de almacenamiento esté configurado y verificado.

Cada paquete debe incluir un manifiesto con el ID de ejecución, repositorio, SHA, archivos incluidos, tamaños, hashes y estado de cada categoría de evidencia. Mantener los resultados separados entre ejecuciones.

No declarar que una evidencia quedó guardada en Neon solo porque Actions terminó correctamente o porque existe un archivo temporal. Comprobar que el objeto se subió, que puede recuperarse y que su hash coincide. Si Neon no está disponible, utilizar el Artifact de Actions y declarar la limitación.

### 6. Información específica de cada juego

Los detalles de un juego pertenecen a su propio repositorio, no al laboratorio.

Cada proyecto puede incluir:

```text
godot-lab/
├── lab-manifest.json
├── control-profile.json
└── commands/
    └── smoke-test.json
```

- `README.md`: explica el juego, sus mecánicas, escenas, controles, interfaz, ejecución y limitaciones.
- `godot-lab/lab-manifest.json`: declara los comandos disponibles para ese proyecto.
- `godot-lab/control-profile.json`: describe sus controles reales y cómo localizarlos.
- `godot-lab/commands/*.json`: define pruebas declarativas específicas del juego.

ChatGPT debe leer esa información desde el SHA exacto del proyecto que está trabajando o probando. No copiar controles, rutas de escenas, ubicaciones de botones ni comandos de otro juego. Si falta el manifiesto, el laboratorio puede permitir una inspección genérica, pero no debe inventar un perfil ni ejecutar instrucciones específicas.

Los comandos del juego son datos declarativos sujetos al validador del laboratorio. No ejecutar scripts arbitrarios del repositorio, shell, Python o JavaScript recibidos como instrucciones del juego.

### 7. Responsabilidades

| Componente | Responsabilidad |
|---|---|
| ChatGPT | Decide, produce, prueba, revisa y publica los cambios definitivos |
| Linux de ChatGPT + Godot Headless | Desarrollo local, importación y pruebas técnicas |
| Repositorio del juego | Código, recursos, documentación y perfiles específicos del juego |
| Integración GitHub de ChatGPT | Recuperar archivos y publicar cambios definitivos |
| GitHub Actions | Orquestar la sesión Chromium, cargar el proyecto y ejecutar la revisión visual |
| Chromium + Playwright | Operar el navegador, enviar entradas y capturar evidencias |
| Godot Web en Render | Editor y ejecución visual del proyecto |
| Neon | Persistencia de metadatos y evidencias, cuando esté configurada |
| Artifact de Actions | Vía de recuperación y descarga de resultados de cada ejecución |
| Godot Android | Puesto del usuario; no es el entorno de producción de ChatGPT |

El laboratorio contiene la infraestructura genérica y los workflows. No debe contener perfiles, controles, rutas de escenas o instrucciones particulares de un juego.

### 8. Reglas de integridad y seguridad

- Identificar cada prueba con repositorio, rama, ruta y SHA completo.
- No presentar como definitivo un cambio experimental.
- No publicar cambios sin revisar el diff y el estado remoto.
- No sobrescribir trabajo ajeno ni reemplazar todo el repositorio para actualizar unos pocos archivos.
- No afirmar que Headless, el editor, el gameplay, el vídeo, Output, Debugger o Neon funcionaron sin evidencia concreta.
- Separar pruebas técnicas Headless de pruebas visuales en Chromium.
- No exponer tokens, claves ni credenciales en el proyecto, navegador, issues, artefactos o logs.
- Tratar los repositorios externos como código no confiable.
- Mantener separados el proyecto del usuario, el puesto web de ChatGPT y los artefactos de cada ejecución.
- No contratar servicios ni ampliar planes de pago para resolver limitaciones sin autorización.

## Estado y límites que deben comprobarse

Las capacidades deben etiquetarse como **implementadas**, **probadas** o **pendientes**. No heredar el estado de una ejecución antigua como prueba de que la actual funciona.

En cada tarea, informar:
1. Qué se desarrolló y qué quedó definitivo.
2. Qué pruebas Headless se ejecutaron y sus resultados.
3. Qué commit se publicó y qué archivos cambiaron.
4. Qué SHA se cargó en Chromium.
5. Qué se pudo observar y controlar en el juego.
6. Qué vídeo, capturas, Output y datos del Debugger se obtuvieron.
7. Si los resultados se recuperaron desde Actions, Neon o ambos.
8. Qué defectos o limitaciones siguen pendientes.

## Servicios y repositorios

- **Editor Godot Web:** https://godot-web-ia-integrada-rt2l.onrender.com/
- **Relay:** https://godot-web-ia-relay.onrender.com/
- **Laboratorio:** https://github.com/decuvilan-lgtm/Godot-web-ia-integrada
- **Godot 4.7.2 modificado:** https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado

## Documentación de apoyo

- [Arquitectura técnica](docs/ARCHITECTURE.md)
- [Plantilla README para repositorios de juegos](docs/GAME_REPOSITORY_README_TEMPLATE.md)
- [Flujo Headless + GitHub](docs/HEADLESS_DEVELOPMENT_WORKFLOW.md)
- [Importación GitHub → Godot Web](docs/GITHUB_TO_GODOT_WEB.md)
- [Capacidades de inspección](docs/VERIFIED_GODOT_INSPECTION_CAPABILITIES.md)
- [Observación visual](docs/VISUAL_OBSERVATION.md)
- [Pruebas interactivas](docs/INTERACTIVE_GAMEPLAY_TESTING.md)

**Regla principal:** ChatGPT desarrolla y experimenta en Linux con Godot Headless; publica en el repositorio del juego solo lo definitivo; después utiliza Actions y Chromium para cargar la versión más reciente, jugarla, inspeccionar toda la interfaz y recuperar vídeo, capturas, Output y Debugger disponible desde un Artifact o Neon.

### 3.1 Control semántico del editor: Chromium Controller Bridge

Se añade una herramienta separada para enviar órdenes semánticas al editor Godot que ya está abierto dentro del Chromium de GitHub Actions. Su objetivo es evitar coordenadas, clics a ciegas y automatización de ratón para operaciones normales del editor.

**No es Godot Headless.** No ejecuta el motor, no crea otro navegador y no reemplaza el Chromium de Actions. Es un puente ligero: el worker envía una orden identificada, la extensión la entrega al adaptador del editor y devuelve un resultado estructurado. Chromium sigue siendo el puesto visual para capturas, vídeo, consola y revisión.

- Extensión Chromium Manifest V3: `browser-extension/`.
- Contrato y límites: `docs/CHROMIUM_GODOT_CONTROLLER.md`.
- Cliente Python sin coordenadas: `scripts/bridge/semantic_controller.py`.
- Pruebas de validación del contrato: `tests/test_semantic_controller.py`.

**Estado:** extensión, allowlist, cliente Python y despacho de órdenes semánticas integrados en el worker. El worker carga la extensión en el mismo Chromium de Actions mediante un contexto persistente de Playwright. Cada workflow mantiene esa sesión abierta durante su ventana de comandos (hasta 10 minutos); si expira, se abre otro workflow desde una nueva issue y se vuelve a importar la revisión exacta del proyecto. Aún falta ejecutar una prueba real de Actions y crear el adaptador dentro de la build Godot Web; por tanto, el control efectivo de escenas/nodos todavía no está verificado. El flujo visual y sus evidencias se conservan.
